from __future__ import annotations

from datetime import datetime, timezone

from bot.live_runner import LiveScanResult
from bot.position_manager import PositionManager
from bot.position_health import assess_position_health
from bot.position_sizer import PositionSizer
from bot.virtual_portfolio import VirtualPortfolio


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

    def __init__(self, max_position_weight: float = 0.35, take_profit: float = 0.0015):
        self.position_manager = PositionManager(take_profit=take_profit)
        self.max_position_weight = max_position_weight

    def execute(
        self,
        portfolio: VirtualPortfolio,
        scan: LiveScanResult,
        eligible_buy_tickers: set[str] | None = None,
        eligible_buy_reasons: dict[str, str] | None = None,
    ) -> tuple[list, list]:
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
        execution_prices = {
            ticker: price
            for ticker, price in scan.current_prices.items()
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
                completed_candles = [
                    candle for candle in (getattr(scan, "candle_history", {}) or {}).get(ticker, ())
                    if getattr(candle, "is_complete", True) is not False
                ]
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
                f"review_required={bool(position is not None and (getattr(position, 'quote_unavailable_cycles', 0) >= 3 or broker_status.get('resolution') == 'UNRESOLVED' or (broker_status.get('status_check_succeeded') and broker_status.get('api_trade_available') is False)))} "
                f"candles_checked={health.candles_checked} flat_sessions={health.flat_sessions} "
                f"recent_range_pct={health.recent_range_pct if health.recent_range_pct is not None else 'UNAVAILABLE'} "
                f"spread={spread_label} exit_action={decision.action} "
                f"exit_reason={decision.reason}"
            )
        for decision in decisions:
            if decision.action == "SELL":
                print(
                    f"SELL_DECISION: ticker={decision.ticker} "
                    f"reason={decision.reason} "
                    f"verified_execution_price={execution_prices.get(decision.ticker, 'UNAVAILABLE')}"
                )

        sell_trades = self.position_manager.execute_sales(
            portfolio,
            decisions,
            execution_prices,
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
                print(
                    f"SELL_EXECUTED: ticker={trade.ticker} "
                    f"quantity={trade.quantity} price={trade.price} "
                    f"realized_pnl={trade.realized_pnl:.6f} "
                    f"reason={trade.reason}"
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

        print(
            f"EXECUTION DIAGNOSTIC: buy_signals={len(eligible_buy_tickers) if eligible_buy_tickers is not None else 'UNFILTERED'} "
            f"ranked_candidates={len(scan.buy_candidates)} "
            f"eligible_for_sizing={len(eligible_analyses)} "
            f"cash={portfolio.cash:.2f} RUB "
            f"active_fresh_tickers={len(active_tickers) if active_tickers is not None else 'UNVERIFIED'}"
        )
        if rejection_counts:
            print(f"EXECUTION REJECTION COUNTS: {rejection_counts}")

        sizer = PositionSizer(
            commission_rate=portfolio.commission_rate,
            max_position_weight=self.max_position_weight,
        )
        sizing_analyses = list(eligible_analyses)
        plans = sizer.plan(
            cash=portfolio.cash,
            analyses=list(sizing_analyses),
            prices=scan.current_prices,
            lot_sizes=scan.lot_sizes,
            existing_positions=set(portfolio.positions),
            existing_values=existing_values,
            total_equity=total_equity,
        )

        # If the ranked shortlist has no feasible allocation (often because its
        # cheapest whole lot exceeds remaining cash), retry with other analyzed
        # instruments only when DecisionEngine explicitly approved BUY and the
        # broker confirmed both a fresh quote and active trading eligibility.
        # This preserves every risk/cash/lot constraint and does not lower AI
        # thresholds or spend the protected profit reserve.
        if not plans and eligible_buy_tickers is not None:
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
                )

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
                    print(
                        "POSITION SIZER REJECTED ALL: sufficient cash for at least one lot, "
                        "but no allocation satisfied cash/position-weight constraints."
                    )
        elif plans:
            print(
                f"POSITION SIZER PLANS: {len(plans)}; "
                + ", ".join(
                    f"{plan.ticker} qty={plan.quantity} cost={plan.total_cost:.2f} RUB"
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
            purchase_time = datetime.now(timezone.utc)
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
    ) -> set[str]:
        """Block re-entry after a SELL while the ticker remains weak.

        The block is derived from the persistent trade history, so it survives
        between cycles and process restarts without adding another database field.
        Once the signal recovers, the ticker becomes eligible again.
        """
        last_trade_by_ticker = {}
        for trade in portfolio.trades:
            last_trade_by_ticker[trade.ticker] = trade

        blocked = set()
        for ticker, trade in last_trade_by_ticker.items():
            if trade.side != "SELL":
                continue

            analysis = analyses.get(ticker)
            if analysis is None:
                blocked.add(ticker)
                continue

            if analysis.momentum <= -0.02 and analysis.trend_strength < 0:
                blocked.add(ticker)

        return blocked
