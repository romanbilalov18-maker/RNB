from __future__ import annotations

from datetime import datetime, timezone
import math

from bot.live_runner import LiveScanResult
from bot.position_manager import PositionDecision, PositionManager
from bot.position_health import assess_position_health, verified_completed_candles
from bot.position_manager import position_take_profit_price
from bot.net_profit_guard import assess_net_profit
from bot.position_sizer import PositionSizer
from bot.protective_stops import average_true_range, initial_atr_stop, market_price_number, ratchet_trailing_stop
from bot.virtual_portfolio import VirtualPortfolio


def _valid_daily_ohlc(candle: object) -> bool:
    """Return whether a daily OHLC bar is internally consistent and priceable."""
    open_price = market_price_number(getattr(candle, "open", None))
    high = market_price_number(getattr(candle, "high", None))
    low = market_price_number(getattr(candle, "low", None))
    if open_price is None or high is None or low is None:
        return False
    return high >= max(open_price, low) and low <= min(open_price, high)


def _daily_ohlc_protective_exit(
    position,
    candle: object,
    *,
    commission_rate: float,
    stop_loss: float,
    take_profit: float,
    take_profit_r_multiple: float | None = None,
) -> tuple[float, str] | None:
    """Resolve a pre-existing holding's protective exit from one real daily bar.

    If both stop and target were touched and daily OHLC cannot reveal order,
    choose the stop first. This is deliberately conservative, not a claim about
    the true intraday path.
    """
    try:
        open_price = market_price_number(getattr(candle, "open"))
        high = market_price_number(getattr(candle, "high"))
        low = market_price_number(getattr(candle, "low"))
        average = float(position.average_price)
        rate = float(commission_rate)
    except (TypeError, ValueError, AttributeError, OverflowError):
        return None
    if open_price is None or high is None or low is None:
        return None
    values = (open_price, high, low, average, rate)
    if not all(math.isfinite(value) for value in values):
        return None
    if min(open_price, high, low, average) <= 0 or not 0 <= rate < 1:
        return None
    if high < max(open_price, low) or low > min(open_price, high):
        return None

    entry_cost = average * (1.0 + rate)
    persisted_stop = getattr(position, "stop_price", None)
    legacy_stop_price = entry_cost * (1.0 + stop_loss) / (1.0 - rate)
    if (
        isinstance(persisted_stop, (int, float))
        and not isinstance(persisted_stop, bool)
        and math.isfinite(persisted_stop)
        and persisted_stop > 0
    ):
        # The tighter (higher) long stop wins. ATR must never weaken the
        # existing hard percentage loss guard.
        stop_price = max(float(persisted_stop), legacy_stop_price)
    else:
        stop_price = legacy_stop_price
    target_price = position_take_profit_price(
        position, rate, take_profit, take_profit_r_multiple
    )

    if open_price <= stop_price:
        return open_price, "исторический Stop Loss: гэп ниже защитного уровня"
    if open_price >= target_price:
        return open_price, "исторический Take Profit: гэп выше целевого уровня"
    stop_touched = low <= stop_price
    target_touched = high >= target_price
    if stop_touched and target_touched:
        return stop_price, (
            "исторический Stop Loss: стоп и цель затронуты в одной дневной свече; "
            "неоднозначный путь, консервативно выбран стоп первым"
        )
    if stop_touched:
        return stop_price, "исторический Stop Loss: внутридневное касание уровня"
    if target_touched:
        return target_price, "исторический Take Profit: внутридневное касание уровня"
    return None


class PaperExecutor:
    """Execute virtual sells first, then size new virtual buys."""

    @staticmethod
    def _has_valid_market_sizing_data(scan: LiveScanResult, ticker: str) -> bool:
        price = scan.current_prices.get(ticker)
        lot_size = scan.lot_sizes.get(ticker)
        return (
            isinstance(price, (int, float))
            and not isinstance(price, bool)
            and 0 < price < float("inf")
            and isinstance(lot_size, int)
            and not isinstance(lot_size, bool)
            and lot_size > 0
        )

    def __init__(
        self,
        max_position_weight: float = 0.35,
        take_profit: float = 0.0015,
        risk_budget_pct: float = 0.01,
        take_profit_r_multiple: float | None = None,
        reentry_cooldown_sessions: int = 0,
        estimated_slippage_bps: float = 1.0,
        fallback_spread_pct: float = 0.0002,
        minimum_net_return: float = 0.0,
    ):
        if (
            isinstance(risk_budget_pct, bool)
            or not isinstance(risk_budget_pct, (int, float))
            or not 0 < risk_budget_pct <= 1
        ):
            raise ValueError("risk_budget_pct must be in (0, 1]")
        if (
            isinstance(reentry_cooldown_sessions, bool)
            or not isinstance(reentry_cooldown_sessions, int)
            or reentry_cooldown_sessions < 0
        ):
            raise ValueError("reentry_cooldown_sessions must be a non-negative integer")
        self.position_manager = PositionManager(
            take_profit=take_profit,
            take_profit_r_multiple=take_profit_r_multiple,
        )
        self.max_position_weight = max_position_weight
        self.risk_budget_pct = float(risk_budget_pct)
        self.reentry_cooldown_sessions = reentry_cooldown_sessions
        # Cost assumptions are explicit and validated by the shared guard.
        assess_net_profit(
            expected_gross_return=0.0,
            commission_rate=0.0,
            spread_pct=fallback_spread_pct,
            slippage_bps=estimated_slippage_bps,
            minimum_net_return=minimum_net_return,
        )
        self.minimum_net_return = float(minimum_net_return)
        self.estimated_slippage_bps = float(estimated_slippage_bps)
        self.fallback_spread_pct = float(fallback_spread_pct)

    @staticmethod
    def _remaining_risk_budget(
        portfolio: VirtualPortfolio,
        total_equity: float,
        configured_risk_budget_pct: float,
        stop_loss_pct: float,
    ) -> tuple[float, float, float]:
        """Return (remaining budget pct, open-position risk, total risk cap).

        Open risk is estimated from each holding's cost basis and the same
        stop-loss/commission model used for proposed entries. Invalid position
        state fails closed instead of authorizing new risk.
        """
        # Keep each bound explicit: the stop-loss rate is strictly positive,
        # while equity and the configured risk budget have their own bounds.
        for label, value in (
            ("total_equity", total_equity),
            ("configured_risk_budget_pct", configured_risk_budget_pct),
            ("stop_loss_pct", stop_loss_pct),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{label} is outside valid range")

        if total_equity <= 0:
            raise ValueError("total_equity is outside valid range")
        if not 0 < configured_risk_budget_pct <= 1:
            raise ValueError("configured_risk_budget_pct is outside valid range")
        if not 0 < stop_loss_pct <= 1:
            raise ValueError("stop_loss_pct is outside valid range")

        commission_rate = portfolio.commission_rate
        if (
            isinstance(commission_rate, bool)
            or not isinstance(commission_rate, (int, float))
            or not math.isfinite(commission_rate)
            or not 0.0 <= commission_rate <= 1.0
        ):
            raise ValueError("commission_rate is outside valid range")
        loss_rate_after_commission = (
            stop_loss_pct
            + 2.0 * commission_rate
            - stop_loss_pct * commission_rate
        )
        if not math.isfinite(loss_rate_after_commission) or loss_rate_after_commission < 0:
            raise ValueError("loss rate after commission is invalid")
        open_risk = 0.0
        for ticker, position in portfolio.positions.items():
            quantity = getattr(position, "quantity", None)
            average_price = getattr(position, "average_price", None)
            if (
                isinstance(quantity, bool)
                or not isinstance(quantity, int)
                or quantity <= 0
                or isinstance(average_price, bool)
                or not isinstance(average_price, (int, float))
                or not math.isfinite(average_price)
                or average_price <= 0
            ):
                raise ValueError(
                    f"cannot estimate open stop-loss risk for invalid position {ticker}"
                )
            current_stop = getattr(position, "stop_price", None)
            if (
                isinstance(current_stop, (int, float))
                and not isinstance(current_stop, bool)
                and math.isfinite(current_stop)
                and current_stop > 0
            ):
                legacy_stop = (
                    average_price * (1.0 + commission_rate)
                    * (1.0 - stop_loss_pct)
                    / (1.0 - commission_rate)
                    if commission_rate < 1.0
                    else current_stop
                )
                effective_stop = max(float(current_stop), legacy_stop)
                current_loss_per_share = max(
                    0.0,
                    average_price * (1.0 + commission_rate)
                    - effective_stop * (1.0 - commission_rate),
                )
                open_risk += quantity * current_loss_per_share
            else:
                persisted_initial_risk = getattr(
                    position, "initial_stop_risk_per_share", None
                )
                if (
                    isinstance(persisted_initial_risk, (int, float))
                    and not isinstance(persisted_initial_risk, bool)
                    and math.isfinite(persisted_initial_risk)
                    and persisted_initial_risk > 0
                ):
                    open_risk += quantity * persisted_initial_risk
                else:
                    open_risk += quantity * average_price * loss_rate_after_commission
            if not math.isfinite(open_risk):
                raise ValueError("open-position stop-loss risk is not finite")

        total_risk_cap = total_equity * configured_risk_budget_pct
        remaining_risk = max(0.0, total_risk_cap - open_risk)
        remaining_pct = remaining_risk / total_equity
        return remaining_pct, open_risk, total_risk_cap

    def execute(
        self,
        portfolio: VirtualPortfolio,
        scan: LiveScanResult,
        eligible_buy_tickers: set[str] | None = None,
        eligible_buy_reasons: dict[str, str] | None = None,
        *,
        as_of: datetime | None = None,
        execution_candles: dict[str, object] | None = None,
    ) -> tuple[list, list]:
        # as_of pins execution to historical time; otherwise use wall clock.
        execution_time = as_of or datetime.now(timezone.utc)
        if execution_time.tzinfo is None or execution_time.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        active_tickers = getattr(scan, "active_trading_tickers", None)
        active_analyses = {
            ticker: analysis
            for ticker, analysis in scan.analyses.items()
            if active_tickers is None or ticker in active_tickers
        }
        # Strategy-based exits require complete, verified entry metadata and a
        # matching current exchange session. Legacy/incomplete positions are not
        # assigned invented purchase details: they may use hard price-based
        # Take Profit/Stop Loss rules on a verified fresh exit quote only.
        sellable_quote_tickers = set(getattr(scan, "sellable_quote_tickers", set()) or set())
        exit_eligible_tickers = set()
        for ticker, position in portfolio.positions.items():
            entry_timestamp = position.purchase_timestamp
            entry_session = position.purchase_session
            entry_exchange = position.purchase_exchange
            has_complete_entry_metadata = bool(
                entry_timestamp and entry_session and str(entry_session).strip()
                and entry_exchange and str(entry_exchange).strip()
            )
            has_any_entry_metadata = bool(
                entry_timestamp or entry_session or entry_exchange
            )
            if not has_any_entry_metadata:
                active_analyses.pop(ticker, None)
                print(
                    f"POSITION LEGACY GUARD: {ticker} has no recorded entry metadata; "
                    "strategy-based exit disabled; verified-price Take Profit/Stop Loss only."
                )
            elif not has_complete_entry_metadata:
                active_analyses.pop(ticker, None)
                print(
                    f"POSITION METADATA GUARD: {ticker} has partial entry metadata; "
                    "strategy-based exit disabled; verified-price Take Profit/Stop Loss remain enabled."
                )
            else:
                current_session_info = (getattr(scan, "session_by_ticker", {}) or {}).get(ticker, {})
                current_session = current_session_info.get("session")
                current_exchange = current_session_info.get("instrument_exchange")
                session_mismatch = (
                    not current_session
                    or str(current_session).strip().casefold() != str(entry_session).strip().casefold()
                    or not current_exchange
                    or str(current_exchange).strip().casefold() != str(entry_exchange).strip().casefold()
                )
                if session_mismatch:
                    # A session mismatch blocks only model/strategy exits. Hard
                    # price guards are session-independent and must still run
                    # against a verified executable quote.
                    active_analyses.pop(ticker, None)
                    print(
                        f"POSITION SESSION GUARD: {ticker} strategy exit disabled; "
                        "verified-price Take Profit/Stop Loss remain enabled; "
                        f"entry_session={entry_session} "
                        f"current_session={current_session or 'UNKNOWN'} "
                        f"entry_exchange={entry_exchange} "
                        f"current_exchange={current_exchange or 'UNKNOWN'}"
                    )

            # A fresh, timestamp-verified order-book bid may authorize evaluating
            # an exit even when the last-trade quote is stale. It never authorizes
            # a new entry. Without either quote source, do not invent an execution price.
            if active_tickers is not None and ticker not in active_tickers and ticker not in sellable_quote_tickers:
                active_analyses.pop(ticker, None)
                print(
                    f"POSITION EXECUTION GUARD: {ticker} has no current fresh last-trade quote or verified fresh bid; exit evaluation skipped."
                )
                continue
            if active_tickers is not None and ticker not in active_tickers and ticker in sellable_quote_tickers:
                print(
                    f"POSITION EXIT FALLBACK: {ticker} using timestamp-verified fresh order-book bid; BUY eligibility remains disabled."
                )
            exit_eligible_tickers.add(ticker)
        # Historical execution opens are a separate, broker-observed channel.
        # Merge them only for already-held positions; never feed them back into
        # candidate ranking, signal analysis, or portfolio mark-to-market inputs.
        available_exit_prices = dict(scan.current_prices)
        available_exit_prices.update(
            getattr(scan, "execution_prices", {}) or {}
        )
        execution_prices = {
            ticker: price
            for ticker, price in available_exit_prices.items()
            if ticker in exit_eligible_tickers
        }
        market_closed_tickers = set(getattr(scan, "market_closed_tickers", set()) or set())
        if active_tickers is not None and not active_tickers and not sellable_quote_tickers:
            closed_count = sum(ticker in market_closed_tickers for ticker in portfolio.positions)
            print(
                "EXECUTION DIAGNOSTIC: no instruments passed active-session + fresh-quote "
                f"checks; confirmed_closed_holdings={closed_count}/{len(portfolio.positions)}."
            )

        decisions = self.position_manager.evaluate(
            portfolio,
            active_analyses,
            execution_prices,
        )
        # Historical daily OHLC is execution-only: it cannot change signals or
        # create intraday exits for a position bought at this same day's open.
        # Only holdings that existed before this execute() call are considered.
        ohlc_exit_reasons = {}
        for ticker, position in portfolio.positions.items():
            candle = (execution_candles or {}).get(ticker)
            if candle is None or ticker not in execution_prices:
                continue
            if not _valid_daily_ohlc(candle):
                print(
                    f"PROTECTIVE OHLC GUARD UNAVAILABLE: ticker={ticker} "
                    "reason=missing_or_inconsistent_daily_OHLC; "
                    "no historical intraday fill was inferred."
                )
                continue
            protective_exit = _daily_ohlc_protective_exit(
                position,
                candle,
                commission_rate=portfolio.commission_rate,
                stop_loss=self.position_manager.stop_loss,
                take_profit=self.position_manager.take_profit,
                take_profit_r_multiple=self.position_manager.take_profit_r_multiple,
            )
            if protective_exit is None:
                continue
            fill_price, reason = protective_exit
            execution_prices[ticker] = fill_price
            ohlc_exit_reasons[ticker] = reason
        if ohlc_exit_reasons:
            decisions = [
                PositionDecision(
                    item.ticker,
                    "SELL",
                    ohlc_exit_reasons[item.ticker],
                ) if item.ticker in ohlc_exit_reasons else item
                for item in decisions
            ]
        # Emit one auditable status per holding: quote provenance, market-health
        # diagnostics, and the exact rule that did or did not authorize an exit.
        # Missing data is a review state, never an automatic sell instruction.
        for decision in decisions:
            ticker = decision.ticker
            analysis = scan.analyses.get(ticker)
            price_available = ticker in execution_prices
            if ticker in sellable_quote_tickers and ticker in (getattr(scan, "fresh_quote_tickers", set()) or set()):
                quote_source = "fresh_bid_preferred_last_trade_also_fresh"
            elif ticker in sellable_quote_tickers:
                quote_source = "fresh_order_book_bid_last_trade_stale_or_ineligible"
            elif active_tickers is None or ticker in (active_tickers or set()):
                quote_source = "fresh_last_trade_quote"
            else:
                quote_source = "no_verified_fresh_exit_quote"
            health = assess_position_health(
                ticker,
                (getattr(scan, "candle_history", {}) or {}).get(ticker, ()),
                current_price_available=price_available,
                momentum=getattr(analysis, "momentum", None),
                trend_strength=getattr(analysis, "trend_strength", None),
                market_closed=ticker in market_closed_tickers,
            )
            spread = (getattr(scan, "liquidity_spread_ticks_by_ticker", {}) or {}).get(ticker)
            spread_label = f"{float(spread):.2f}_ticks" if isinstance(spread, (int, float)) else "unverified"
            position = portfolio.positions.get(ticker)
            broker_status = (getattr(scan, "instrument_status_by_ticker", {}) or {}).get(ticker, {})
            if not broker_status:
                broker_status = {"resolution": "UNAVAILABLE", "trading_status": "UNAVAILABLE"}
            broker_status_label = (
                f"resolution={broker_status.get('resolution', 'UNAVAILABLE')};"
                f"trading_status={broker_status.get('trading_status', 'UNAVAILABLE')};"
                f"api_trade_available={broker_status.get('api_trade_available', 'UNAVAILABLE')};"
                f"sell_available={broker_status.get('sell_available', 'UNAVAILABLE')};"
                f"status_check_succeeded={broker_status.get('status_check_succeeded', False)}"
            )
            if position is not None:
                if broker_status.get("status_check_succeeded") and broker_status.get("sell_available") is False:
                    health_condition = "EXIT_RESTRICTED"
                elif broker_status.get("resolution") == "UNRESOLVED" or (
                    broker_status.get("status_check_succeeded")
                    and broker_status.get("api_trade_available") is False
                ):
                    health_condition = "BROKER_RESTRICTED"
                elif not price_available:
                    health_condition = "QUOTE_DATA_PROBLEM"
                elif health.status == "PROLONGED_STAGNATION":
                    health_condition = "PROLONGED_STAGNATION"
                else:
                    health_condition = None
                if health_condition != getattr(position, "health_condition", None):
                    position.health_condition = health_condition
                    position.health_condition_since = execution_time.isoformat() if health_condition else None
                if price_available:
                    position.quote_unavailable_cycles = 0
                elif ticker not in market_closed_tickers:
                    position.quote_unavailable_cycles = max(
                        0, int(getattr(position, "quote_unavailable_cycles", 0) or 0)
                    ) + 1
                # This is the current consecutive flat-candle streak, not a
                # lifetime counter. It can fall back to zero when real candles
                # show movement again.
                position.stagnant_sessions = max(0, int(health.flat_sessions or 0))
                position.last_health_status = health.status
                completed_candles = verified_completed_candles(
                    (getattr(scan, "candle_history", {}) or {}).get(ticker, ())
                )
                if completed_candles:
                    candle_time = getattr(completed_candles[-1], "time", None)
                    if candle_time is not None:
                        position.last_health_candle_timestamp = (
                            candle_time.isoformat() if hasattr(candle_time, "isoformat")
                            else str(candle_time)
                        )
            print(
                f"POSITION STATUS: ticker={ticker} quote_source={quote_source} "
                f"price={execution_prices.get(ticker, 'UNAVAILABLE')} "
                f"health={health.status} recommendation={health.recommendation} "
                f"quote_unavailable_cycles={getattr(position, 'quote_unavailable_cycles', 0) if position is not None else 0} "
                f"stagnant_sessions={getattr(position, 'stagnant_sessions', 0) if position is not None else 0} "
                f"broker_instrument_status={broker_status_label} "
                f"review_required={bool(position is not None and (getattr(position, 'quote_unavailable_cycles', 0) >= 3 or health.status == 'PROLONGED_STAGNATION' or broker_status.get('resolution') == 'UNRESOLVED' or (broker_status.get('status_check_succeeded') and (broker_status.get('api_trade_available') is False or broker_status.get('sell_available') is False)) ))} "
                f"candles_checked={health.candles_checked} flat_sessions={health.flat_sessions} "
                f"recent_range_pct={health.recent_range_pct if health.recent_range_pct is not None else 'UNAVAILABLE'} "
                f"spread={spread_label} "
                f"initial_stop={getattr(position, 'initial_stop_price', None) if position is not None else 'UNAVAILABLE'} "
                f"current_stop={getattr(position, 'stop_price', None) if position is not None else 'UNAVAILABLE'} "
                f"high_watermark={getattr(position, 'high_watermark', None) if position is not None else 'UNAVAILABLE'} "
                f"stop_model={getattr(position, 'stop_model', None) if position is not None else 'UNAVAILABLE'} "
                f"exit_action={decision.action} exit_reason={decision.reason}"
            )
        for decision in decisions:
            if decision.action == "SELL":
                print(
                    f"SELL_DECISION: ticker={decision.ticker} "
                    f"reason={decision.reason} "
                    f"verified_execution_price={execution_prices.get(decision.ticker, 'UNAVAILABLE')}"
                )

        position_stop_snapshot = {
            ticker: {
                "quantity": position.quantity,
                "initial_stop_price": getattr(position, "initial_stop_price", None),
                "stop_price": max(
                    float(getattr(position, "stop_price")),
                    position.average_price * (1.0 + portfolio.commission_rate)
                    * (1.0 + self.position_manager.stop_loss)
                    / (1.0 - portfolio.commission_rate),
                ) if (
                    isinstance(getattr(position, "stop_price", None), (int, float))
                    and not isinstance(getattr(position, "stop_price", None), bool)
                    and math.isfinite(getattr(position, "stop_price"))
                    and getattr(position, "stop_price") > 0
                ) else (
                    position.average_price * (1.0 + portfolio.commission_rate)
                    * (1.0 + self.position_manager.stop_loss)
                    / (1.0 - portfolio.commission_rate)
                ),
                "initial_stop_risk_per_share": getattr(
                    position, "initial_stop_risk_per_share", None
                ),
                "stop_model": getattr(position, "stop_model", None),
            }
            for ticker, position in portfolio.positions.items()
        }
        sell_trades = self.position_manager.execute_sales(
            portfolio,
            decisions,
            execution_prices,
            timestamp=execution_time,
        )
        executed_sell_tickers = {trade.ticker for trade in sell_trades}
        for decision in decisions:
            if decision.action != "SELL":
                continue
            if decision.ticker in executed_sell_tickers:
                trade = next(
                    trade for trade in sell_trades
                    if trade.ticker == decision.ticker
                )
                snapshot = position_stop_snapshot.get(trade.ticker, {})
                initial_risk_per_share = snapshot.get("initial_stop_risk_per_share")
                initial_risk = (
                    trade.quantity * initial_risk_per_share
                    if isinstance(initial_risk_per_share, (int, float))
                    and not isinstance(initial_risk_per_share, bool)
                    and math.isfinite(initial_risk_per_share)
                    and initial_risk_per_share > 0
                    else None
                )
                actual_loss = max(0.0, -float(trade.realized_pnl))
                trigger_price = snapshot.get("stop_price")
                stop_slippage = (
                    float(trigger_price) - float(trade.price)
                    if isinstance(trigger_price, (int, float))
                    and not isinstance(trigger_price, bool)
                    and math.isfinite(trigger_price)
                    and trigger_price > 0
                    and ("stop" in str(trade.reason).casefold() or "лимит убытка" in str(trade.reason).casefold())
                    else None
                )
                loss_over_initial_risk = (
                    actual_loss / initial_risk
                    if initial_risk is not None and initial_risk > 0
                    else "UNAVAILABLE"
                )
                print(
                    f"SELL_EXECUTED: ticker={trade.ticker} "
                    f"quantity={trade.quantity} fill_price={trade.price} "
                    f"realized_pnl={trade.realized_pnl:.6f} "
                    f"reason={trade.reason}"
                )
                if "stop" in str(trade.reason).casefold() or "лимит убытка" in str(trade.reason).casefold():
                    print(
                        f"STOP_EXIT_AUDIT: ticker={trade.ticker} "
                        f"model={snapshot.get('stop_model') or 'LEGACY'} "
                        f"initial_stop={snapshot.get('initial_stop_price')} "
                        f"trigger_stop={trigger_price} fill_price={trade.price} "
                        f"gap_slippage_per_share={stop_slippage} "
                        f"actual_loss={actual_loss:.6f} "
                        f"initial_risk={initial_risk if initial_risk is not None else 'UNAVAILABLE'} "
                        f"loss_over_initial_risk={loss_over_initial_risk}"
                    )
            else:
                position = portfolio.positions.get(decision.ticker)
                print(
                    f"SELL_SKIPPED: ticker={decision.ticker} "
                    f"reason=execution_validation_failed "
                    f"position_exists={position is not None} "
                    f"price={execution_prices.get(decision.ticker, 'UNAVAILABLE')}"
                )
        recently_sold = executed_sell_tickers

        # Ratchet trailing stops only after today's protective OHLC check. For
        # historical daily bars this avoids using today's high to create a stop
        # and then retroactively testing today's low against that new stop.
        for ticker, position in portfolio.positions.items():
            current_stop = getattr(position, "stop_price", None)
            if not (
                isinstance(current_stop, (int, float))
                and not isinstance(current_stop, bool)
                and math.isfinite(current_stop)
                and current_stop > 0
            ):
                continue
            atr = average_true_range(
                (getattr(scan, "candle_history", {}) or {}).get(ticker, ()),
                period=14,
            )
            if atr is None:
                continue
            candle = (execution_candles or {}).get(ticker)
            observed_high = (
                market_price_number(getattr(candle, "high", None))
                if candle is not None
                else market_price_number(execution_prices.get(ticker))
            )
            if observed_high is None or not math.isfinite(observed_high) or observed_high <= 0:
                continue
            old_high = getattr(position, "high_watermark", None)
            if not (
                isinstance(old_high, (int, float))
                and not isinstance(old_high, bool)
                and math.isfinite(old_high)
                and old_high > 0
            ):
                old_high = position.average_price
            high_watermark = max(float(old_high), observed_high)
            try:
                raised_stop = ratchet_trailing_stop(
                    float(current_stop), high_watermark, atr, 2.0
                )
            except ValueError:
                continue
            position.high_watermark = high_watermark
            current_mark = execution_prices.get(ticker)
            candle_low = (
                market_price_number(getattr(candle, "low", None))
                if candle is not None
                else None
            )
            if (
                not isinstance(current_mark, (int, float))
                or isinstance(current_mark, bool)
                or not math.isfinite(current_mark)
                or current_mark <= 0
                or raised_stop >= current_mark
                or (
                    candle is not None
                    and (candle_low is None or candle_low <= raised_stop)
                )
            ):
                # Never create a stop above the currently executable mark.
                # For daily OHLC, today's high is used only to prepare a future
                # stop; the current open remains the conservative mark.
                continue
            if raised_stop > float(current_stop) + 1e-12:
                position.stop_price = raised_stop
                position.stop_updated_at = execution_time
                print(
                    f"TRAILING STOP UPDATED: ticker={ticker} "
                    f"high_watermark={high_watermark:.6f} "
                    f"previous_stop={float(current_stop):.6f} "
                    f"new_stop={raised_stop:.6f} atr14={atr:.6f}"
                )

        sell_decision_tickers = {
            decision.ticker
            for decision in decisions
            if decision.action == "SELL"
        }

        existing_values = {
            ticker: position.quantity * scan.current_prices[ticker]
            for ticker, position in portfolio.positions.items()
            if ticker in scan.current_prices
        }
        # Missing quotes for unrelated holdings must not abort execution for
        # eligible instruments. The partial valuation excludes unpriced positions,
        # making position-weight limits conservative rather than inventing prices.
        partial_equity = getattr(portfolio, "equity_with_available_prices", None)
        if callable(partial_equity):
            total_equity, unpriced_positions = partial_equity(scan.current_prices)
        else:
            # Preserve compatibility with lightweight portfolio doubles used by
            # integrations/tests; production VirtualPortfolio implements the
            # quote-aware valuation API above.
            total_equity = portfolio.equity(scan.current_prices)
            unpriced_positions = ()
        if unpriced_positions:
            print(
                "EXECUTION DIAGNOSTIC: portfolio valuation incomplete; "
                f"unpriced_positions={','.join(unpriced_positions)}; "
                "new orders still require fresh prices for their own tickers."
            )
        # After selling, immediately reuse the freed cash. The primary
        # strategy remains TOP-3, but if a TOP-3 candidate is unavailable,
        # walk through the full ranked candidate list from this scan.
        blocked_reentries = self._blocked_reentries(
            portfolio,
            scan.analyses,
            candle_history=(getattr(scan, "candle_history", {}) or {}),
            cooldown_sessions=self.reentry_cooldown_sessions,
        )
        eligible_analyses = []
        rejection_counts = {}
        for analysis in scan.buy_candidates:
            ticker = analysis.ticker
            reasons = []
            if eligible_buy_tickers is not None and ticker not in eligible_buy_tickers:
                reasons.append("DecisionEngine did not authorize BUY")
            if ticker in recently_sold:
                reasons.append("sold this cycle")
            if ticker in sell_decision_tickers:
                reasons.append("PositionManager marked ticker SELL")
            if ticker in blocked_reentries:
                reasons.append("re-entry blocked until weak signal recovers")
            if not self._has_valid_market_sizing_data(scan, ticker):
                if ticker not in scan.current_prices:
                    reasons.append("no verified fresh quote")
                if ticker not in scan.lot_sizes:
                    reasons.append("missing/invalid T-Invest lot size")
                price = scan.current_prices.get(ticker)
                if price is not None and not (
                    isinstance(price, (int, float))
                    and not isinstance(price, bool)
                    and 0 < price < float("inf")
                ):
                    reasons.append("invalid price")
            if active_tickers is not None and ticker not in active_tickers:
                reasons.append("instrument not confirmed active with fresh quote")
            if reasons:
                for reason in reasons:
                    rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                print(f"BUY CANDIDATE REJECTED: {ticker}: {'; '.join(reasons)}")
                continue
            eligible_analyses.append(analysis)

        # Derive an instrument-specific protective level from verified,
        # completed broker candles only. When ATR evidence is insufficient,
        # preserve the existing commission-adjusted 5% stop as an explicit
        # compatibility fallback rather than inventing volatility data.
        stop_prices = {}
        stop_models = {}
        for analysis in scan.analyses.values():
            ticker = getattr(analysis, "ticker", None)
            if not isinstance(ticker, str) or not ticker.strip():
                continue
            if not self._has_valid_market_sizing_data(scan, ticker):
                continue
            entry_price = float(scan.current_prices[ticker])
            atr = average_true_range(
                (getattr(scan, "candle_history", {}) or {}).get(ticker, ()),
                period=14,
            )
            rate = portfolio.commission_rate
            entry_cost = entry_price * (1.0 + rate)
            legacy_stop_price = (
                entry_cost * (1.0 + self.position_manager.stop_loss)
                / (1.0 - rate)
            )
            if atr is not None:
                try:
                    atr_stop_price = initial_atr_stop(entry_price, atr, 2.0)
                    # The ATR level may be wider than the existing hard 5%
                    # net-loss guard. Persist and size from the tighter level.
                    stop_prices[ticker] = max(atr_stop_price, legacy_stop_price)
                    stop_models[ticker] = (
                        "ATR14_X2"
                        if atr_stop_price >= legacy_stop_price
                        else "ATR14_X2_WITH_HARD_5PCT_CAP"
                    )
                    continue
                except ValueError:
                    print(
                        f"PROTECTIVE STOP FALLBACK: ticker={ticker} "
                        "reason=ATR level outside valid price range; using legacy 5% guard."
                    )
            stop_prices[ticker] = legacy_stop_price
            stop_models[ticker] = "FIXED_5PCT_FALLBACK"

        print(
            f"EXECUTION DIAGNOSTIC: buy_signals={len(eligible_buy_tickers) if eligible_buy_tickers is not None else 'UNFILTERED'} "
            f"ranked_candidates={len(scan.buy_candidates)} "
            f"eligible_for_sizing={len(eligible_analyses)} "
            f"cash={portfolio.cash:.2f} RUB "
            f"active_fresh_tickers={len(active_tickers) if active_tickers is not None else 'UNVERIFIED'}"
        )
        if rejection_counts:
            print(f"EXECUTION REJECTION COUNTS: {rejection_counts}")

        remaining_risk_budget_pct, open_position_risk, total_risk_cap = (
            self._remaining_risk_budget(
                portfolio,
                total_equity,
                self.risk_budget_pct,
                abs(self.position_manager.stop_loss),
            )
        )
        print(
            "PORTFOLIO RISK BUDGET: "
            f"open_stop_loss_risk={open_position_risk:.2f} RUB "
            f"configured_cap={total_risk_cap:.2f} RUB "
            f"remaining_for_new_entries={max(0.0, total_risk_cap - open_position_risk):.2f} RUB"
        )
        risk_budget_exhausted = remaining_risk_budget_pct <= 0.0
        sizer = PositionSizer(
            commission_rate=portfolio.commission_rate,
            max_position_weight=self.max_position_weight,
            risk_budget_pct=(
                remaining_risk_budget_pct
                if not risk_budget_exhausted
                else self.risk_budget_pct
            ),
            stop_loss_pct=abs(self.position_manager.stop_loss),
        )
        sizing_analyses = list(eligible_analyses)
        plans = []
        if not risk_budget_exhausted:
            plans = sizer.plan(
                cash=portfolio.cash,
                analyses=list(sizing_analyses),
                prices=scan.current_prices,
                lot_sizes=scan.lot_sizes,
                existing_positions=set(portfolio.positions),
                existing_values=existing_values,
                total_equity=total_equity,
                stop_prices=stop_prices,
            )
        elif sizing_analyses and risk_budget_exhausted:
            print(
                "POSITION SIZER REJECTED ALL: existing open-position stop-loss risk "
                "already meets or exceeds the configured portfolio risk budget."
            )

        # If the ranked shortlist has no feasible allocation (often because its
        # cheapest whole lot exceeds remaining cash), retry with other analyzed
        # instruments only when DecisionEngine explicitly approved BUY and the
        # broker confirmed both a fresh quote and active trading eligibility.
        # This preserves every risk/cash/lot constraint and does not lower AI
        # thresholds or spend the protected profit reserve.
        if not plans and eligible_buy_tickers is not None and not risk_budget_exhausted:
            ranked_tickers = {analysis.ticker for analysis in scan.buy_candidates}
            fresh_tickers = getattr(scan, "fresh_quote_tickers", None)
            fallback_tickers = getattr(scan, "active_trading_tickers", None)
            fallback_analyses = [
                analysis
                for ticker, analysis in scan.analyses.items()
                if ticker not in ranked_tickers
                and ticker in eligible_buy_tickers
                and ticker not in portfolio.positions
                and ticker not in recently_sold
                and ticker not in sell_decision_tickers
                and ticker not in blocked_reentries
                and fresh_tickers is not None
                and ticker in fresh_tickers
                and fallback_tickers is not None
                and ticker in fallback_tickers
                and self._has_valid_market_sizing_data(scan, ticker)
            ]
            fallback_analyses.sort(
                key=lambda item: (
                    -float(getattr(item, "score", 0.0)),
                    -float(getattr(item, "momentum", 0.0)),
                    float(getattr(item, "volatility", float("inf"))),
                    item.ticker,
                )
            )
            if fallback_analyses:
                sizing_analyses.extend(fallback_analyses)
                print(
                    "POSITION SIZER FALLBACK: ranked shortlist had no feasible "
                    f"allocation; retrying with {len(fallback_analyses)} additional "
                    "DecisionEngine-approved instruments with fresh active-session quotes."
                )
                plans = sizer.plan(
                    cash=portfolio.cash,
                    analyses=sizing_analyses,
                    prices=scan.current_prices,
                    lot_sizes=scan.lot_sizes,
                    existing_positions=set(portfolio.positions),
                    existing_values=existing_values,
                    total_equity=total_equity,
                    stop_prices=stop_prices,
                )

        if plans:
            spread_by_ticker = getattr(scan, "liquidity_spread_pct_by_ticker", {}) or {}
            guarded_plans = []
            for plan in plans:
                # Target price is the gross execution price required to deliver
                # configured net Take Profit after round-trip commissions.
                planned_position = type(
                    "_PlannedPosition", (),
                    {
                        "average_price": plan.price,
                        "initial_stop_price": plan.stop_price,
                        "initial_stop_risk_per_share": (
                            plan.price * (1.0 + portfolio.commission_rate)
                            - plan.stop_price * (1.0 - portfolio.commission_rate)
                            if plan.stop_price is not None else None
                        ),
                    },
                )()
                target_price = position_take_profit_price(
                    planned_position, portfolio.commission_rate,
                    self.position_manager.take_profit,
                    self.position_manager.take_profit_r_multiple,
                )
                spread_pct = spread_by_ticker.get(plan.ticker)
                spread_source = "T_INVEST_ORDER_BOOK"
                if (
                    isinstance(spread_pct, bool)
                    or not isinstance(spread_pct, (int, float))
                    or not math.isfinite(spread_pct)
                    or spread_pct < 0
                ):
                    spread_pct = self.fallback_spread_pct
                    spread_source = "CONFIGURED_FALLBACK"
                assessment = assess_net_profit(
                    expected_gross_return=target_price / plan.price - 1.0,
                    commission_rate=portfolio.commission_rate,
                    spread_pct=float(spread_pct),
                    slippage_bps=self.estimated_slippage_bps,
                    minimum_net_return=self.minimum_net_return,
                )
                if not assessment.allowed:
                    print(
                        f"NET PROFIT GUARD REJECTED: ticker={plan.ticker} "
                        f"net_return={assessment.expected_net_return * 100:.4f}% "
                        f"commission={assessment.round_trip_commission * 100:.4f}% "
                        f"spread={assessment.spread_cost * 100:.4f}% "
                        f"slippage={assessment.slippage_cost * 100:.4f}% "
                        f"spread_source={spread_source} reason={assessment.reason}"
                    )
                    continue
                print(
                    f"NET PROFIT GUARD PASSED: ticker={plan.ticker} "
                    f"net_return={assessment.expected_net_return * 100:.4f}% "
                    f"spread_source={spread_source}"
                )
                guarded_plans.append(plan)
            plans = guarded_plans

        if sizing_analyses and not plans:
            min_lot_costs = []
            for analysis in sizing_analyses:
                price = scan.current_prices[analysis.ticker]
                lot_size = scan.lot_sizes[analysis.ticker]
                min_lot_costs.append(
                    (price * lot_size * (1.0 + portfolio.commission_rate), analysis.ticker, lot_size)
                )
            if min_lot_costs:
                minimum_cost, minimum_ticker, minimum_lot = min(min_lot_costs)
                if minimum_cost > portfolio.cash:
                    print(
                        f"POSITION SIZER REJECTED ALL: cash={portfolio.cash:.2f} RUB; "
                        f"cheapest eligible lot={minimum_ticker} x {minimum_lot} "
                        f"costs {minimum_cost:.2f} RUB including commission."
                    )
                else:
                    risk_inputs = (
                        sizer.stop_loss_pct,
                        sizer.commission_rate,
                        sizer.risk_budget_pct,
                        portfolio.commission_rate,
                        total_equity,
                    )
                    if all(
                        isinstance(value, (int, float))
                        and not isinstance(value, bool)
                        and math.isfinite(value)
                        for value in risk_inputs
                    ):
                        minimum_stop = stop_prices.get(minimum_ticker)
                        minimum_entry = scan.current_prices[minimum_ticker]
                        minimum_lot_risk = (
                            minimum_lot * (
                                minimum_entry * (1.0 + portfolio.commission_rate)
                                - minimum_stop * (1.0 - portfolio.commission_rate)
                            )
                            if minimum_stop is not None
                            else minimum_cost / (1.0 + portfolio.commission_rate)
                            * (
                                sizer.stop_loss_pct
                                + 2.0 * sizer.commission_rate
                                - sizer.stop_loss_pct * sizer.commission_rate
                            )
                        )
                        risk_budget = total_equity * remaining_risk_budget_pct
                        if minimum_lot_risk > risk_budget + 1e-9:
                            print(
                                "POSITION SIZER REJECTED ALL: minimum whole-lot stop-loss risk "
                                f"for {minimum_ticker} is {minimum_lot_risk:.2f} RUB, above "
                                f"the configured risk budget {risk_budget:.2f} RUB "
                                f"({sizer.risk_budget_pct * 100:.2f}% of equity); no order submitted."
                            )
                        else:
                            print(
                                "POSITION SIZER REJECTED ALL: sufficient cash and per-lot risk, "
                                "but no allocation satisfied cash/position-weight constraints."
                            )
                    else:
                        print(
                            "POSITION SIZER REJECTED ALL: no feasible allocation; "
                            "risk diagnostic inputs are unavailable."
                        )
        elif plans:
            print(
                f"POSITION SIZER PLANS: {len(plans)}; "
                + ", ".join(
                    f"{plan.ticker} qty={plan.quantity} cost={plan.total_cost:.2f} RUB risk={plan.estimated_stop_loss_risk:.2f} RUB"
                    for plan in plans
                )
            )

        buy_trades = []
        for plan in plans:
            if (
                plan.ticker in portfolio.positions
                or plan.ticker in recently_sold
                or plan.ticker in sell_decision_tickers
            ):
                continue
            purchase_time = execution_time
            trade = portfolio.buy(
                ticker=plan.ticker,
                quantity=plan.quantity,
                price=plan.price,
                timestamp=purchase_time,
                reason=(eligible_buy_reasons or {}).get(
                    plan.ticker, "BUY accepted by PositionSizer"
                ),
            )
            position = portfolio.positions[plan.ticker]
            if position.initial_stop_price is None and plan.stop_price is not None:
                stop_price = float(plan.stop_price)
                position.initial_stop_price = stop_price
                position.stop_price = stop_price
                position.high_watermark = float(plan.price)
                position.initial_stop_risk_per_share = (
                    float(plan.price) * (1.0 + portfolio.commission_rate)
                    - stop_price * (1.0 - portfolio.commission_rate)
                )
                position.stop_model = stop_models.get(
                    plan.ticker, "FIXED_5PCT_FALLBACK"
                )
                position.stop_updated_at = execution_time
                print(
                    f"PROTECTIVE STOP INITIALIZED: ticker={plan.ticker} "
                    f"model={position.stop_model} entry={plan.price:.6f} "
                    f"initial_stop={stop_price:.6f} "
                    f"risk_per_share={position.initial_stop_risk_per_share:.6f}"
                )
            # Preserve the original entry session when averaging into an existing
            # position; initialize metadata only for a newly opened position.
            if position.purchase_timestamp is None:
                session_info = (getattr(scan, "session_by_ticker", {}) or {}).get(plan.ticker, {})
                if self._record_entry_metadata(position, purchase_time, session_info):
                    print(
                        f"POSITION ENTRY METADATA: {plan.ticker} "
                        f"purchase_timestamp={position.purchase_timestamp.isoformat()} "
                        f"purchase_session={position.purchase_session} "
                        f"purchase_exchange={position.purchase_exchange}"
                    )
                else:
                    print(
                        f"POSITION ENTRY METADATA UNAVAILABLE: {plan.ticker}; "
                        "session/exchange missing, position metadata left entirely unset."
                    )
            buy_trades.append(trade)

        return sell_trades, buy_trades

    @staticmethod
    def _record_entry_metadata(position, purchase_time, session_info: dict) -> bool:
        """Persist complete entry provenance, or leave legacy metadata untouched."""
        session = session_info.get("session")
        exchange = session_info.get("instrument_exchange")
        if not session or not str(session).strip() or not exchange or not str(exchange).strip():
            return False
        if position.purchase_timestamp is not None:
            return True
        position.purchase_timestamp = purchase_time
        position.purchase_session = str(session).strip()
        position.purchase_exchange = str(exchange).strip()
        return True

    @staticmethod
    def _blocked_reentries(
        portfolio: VirtualPortfolio,
        analyses: dict,
        *,
        candle_history: dict | None = None,
        cooldown_sessions: int = 0,
    ) -> set[str]:
        """Block weak re-entries and count only completed broker sessions after a stop."""
        if (
            isinstance(cooldown_sessions, bool)
            or not isinstance(cooldown_sessions, int)
            or cooldown_sessions < 0
        ):
            raise ValueError("cooldown_sessions must be a non-negative integer")
        last_trade_by_ticker = {}
        for trade in portfolio.trades:
            last_trade_by_ticker[trade.ticker] = trade
        blocked = set()
        candle_history = candle_history or {}
        for ticker, trade in last_trade_by_ticker.items():
            if trade.side != "SELL":
                continue
            is_stop_exit = (
                "stop" in str(getattr(trade, "reason", "")).casefold()
                or "лимит убытка" in str(getattr(trade, "reason", "")).casefold()
            )
            if cooldown_sessions and is_stop_exit:
                sell_time = getattr(trade, "timestamp", None)
                completed = verified_completed_candles(candle_history.get(ticker, ()))
                later_sessions = sum(
                    1 for candle in completed
                    if isinstance(getattr(candle, "time", None), datetime)
                    and isinstance(sell_time, datetime)
                    and candle.time > sell_time
                )
                if later_sessions < cooldown_sessions:
                    blocked.add(ticker)
                    continue
            analysis = analyses.get(ticker)
            if analysis is None:
                blocked.add(ticker)
                continue
            if analysis.momentum <= -0.02 and analysis.trend_strength < 0:
                blocked.add(ticker)
        return blocked
