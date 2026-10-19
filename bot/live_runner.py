from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import time
import math

from bot.stock_analysis import StockAnalysis, StockAnalyzer
from bot.market_context import build_market_context
from bot.market_context.clock import current_times
from bot.market_context.trading_schedule import (
    ExchangeSession,
    normalize_exchange,
    resolve_exchange_session,
)


@dataclass(frozen=True)
class LiveScanResult:
    selected_10: list[object]
    selected_3: list[StockAnalysis]
    buy_candidates: list[StockAnalysis]
    analyses: dict[str, StockAnalysis]
    current_prices: dict[str, float]
    previous_closes: dict[str, float]
    lot_sizes: dict[str, int]
    active_trading_tickers: set[str] | None = None
    fresh_quote_tickers: set[str] = field(default_factory=set)
    liquidity_by_ticker: dict[str, float] = field(default_factory=dict)
    liquidity_spread_ticks_by_ticker: dict[str, float] = field(default_factory=dict)
    latest_candles: dict[str, object] = field(default_factory=dict)
    candle_history: dict[str, list[object]] = field(default_factory=dict)
    sector_by_ticker: dict[str, str] = field(default_factory=dict)
    sector_returns: dict[str, float] = field(default_factory=dict)
    market_return: float | None = None
    market_breadth: float | None = None
    market_sample_count: int = 0
    market_context: object | None = None
    session_by_ticker: dict[str, dict] = field(default_factory=dict)


class LiveMarketRunner:
    """Run one real-market analysis cycle using T-Invest market data only."""

    def __init__(self, client, history_days: int = 30):
        if history_days <= 0:
            raise ValueError("history_days must be positive")
        self.client = client
        self.history_days = history_days
        self.analyzer = StockAnalyzer(min_history=20, momentum_period=10)
        # Quotes older than this limit are diagnostic only and cannot authorize trading.
        self.max_quote_age_seconds = self._positive_env_float(
            "TINVEST_MAX_QUOTE_AGE_SECONDS", 300.0
        )
        # Analyze a wider real-market shortlist by default. Keep configurable
        # because historical-candle requests are rate-limited by the broker.
        self.max_analysis_instruments = self._positive_env_int(
            "TINVEST_MAX_ANALYSIS_INSTRUMENTS", 50
        )
        self.schedule_cache_ttl_seconds = self._positive_env_float(
            "TINVEST_SCHEDULE_CACHE_SECONDS", 300.0
        )
        self._schedule_cache_at: datetime | None = None
        self._schedule_cache: dict[str, object] = {}

    def run(
        self,
        held_tickers: set[str] | None = None,
        tracked_tickers: set[str] | None = None,
    ) -> LiveScanResult:
        held_tickers = held_tickers or set()
        tracked_tickers = tracked_tickers or set()
        # Stamp the cycle before any market-data request. Calendar heuristics do
        # not authorize trades; broker instrument statuses are checked below.
        cycle_utc, cycle_moscow = current_times()
        initial_context = build_market_context(cycle_utc)
        print(
            f"Trading decision clock: date_moscow={cycle_moscow.date().isoformat()} "
            f"weekday={initial_context.weekday} time_moscow={cycle_moscow.strftime('%H:%M:%S %Z')} "
            f"utc={cycle_utc.isoformat()} timezone=Europe/Moscow"
        )
        print(
            f"Market context: utc={cycle_utc.isoformat()} "
            f"moscow={cycle_moscow.isoformat()} weekday={initial_context.weekday} "
            f"calendar={initial_context.calendar_status} session=awaiting_t_invest_status"
        )

        shares_response = self.client.instruments.shares()
        shares = [
            share for share in shares_response.instruments
            if self._is_tradable_rub_share(share)
        ]
        if not shares:
            raise RuntimeError("T-Invest returned no tradable RUB shares")

        shares_by_ticker = {
            str(getattr(share, "ticker", "") or ""): share
            for share in shares
            if str(getattr(share, "ticker", "") or "")
        }

        # Positions are persisted by ticker, so report the exact broker metadata
        # resolution rather than guessing a UID/FIGI for an unresolved holding.
        for held_ticker in sorted(held_tickers):
            held_share = shares_by_ticker.get(held_ticker)
            if held_share is None:
                print(
                    f"Held-position instrument mapping: ticker={held_ticker} "
                    "instrument_uid=UNRESOLVED figi=UNRESOLVED exchange=UNRESOLVED "
                    "reason=not_in_tradable_RUB_share_universe"
                )
                continue
            print(
                f"Held-position instrument mapping: ticker={held_ticker} "
                f"instrument_uid={getattr(held_share, 'uid', '') or 'UNAVAILABLE'} "
                f"figi={getattr(held_share, 'figi', '') or 'UNAVAILABLE'} "
                f"exchange={getattr(held_share, 'exchange', '') or 'UNAVAILABLE'}"
            )
        schedule_map, schedule_fetch_succeeded = self._load_trading_schedules(cycle_utc)
        if schedule_fetch_succeeded:
            print(
                f"T-Invest schedule loaded: {len(schedule_map)} exchanges; "
                f"cache_ttl={self.schedule_cache_ttl_seconds:g}s"
            )
        else:
            print("T-Invest schedule unavailable; all instruments without verified schedules stay ineligible.")

        instrument_ids = [
            str(getattr(share, "uid", "") or getattr(share, "figi", ""))
            for share in shares
        ]
        instrument_ids = [value for value in instrument_ids if value]

        prices_response = self.client.market_data.get_last_prices(
            instrument_id=instrument_ids,
        )

        from t_tech.invest import InstrumentClosePriceRequest

        close_response = self.client.market_data.get_close_prices(
            instruments=[
                InstrumentClosePriceRequest(instrument_id=instrument_id)
                for instrument_id in instrument_ids
            ],
        )

        last_prices = {
            self._instrument_key(item): self._quotation(item.price)
            for item in prices_response.last_prices
            if self._quotation(item.price) > 0
        }
        # Keep source timestamps for diagnostics; a positive price alone does not
        # prove that the quote is fresh or belongs to the current session.
        last_price_items = {
            self._instrument_key(item): item
            for item in prices_response.last_prices
            if self._quotation(item.price) > 0
        }
        close_prices = {
            self._instrument_key(item): self._quotation(item.price)
            for item in close_response.close_prices
            if self._quotation(item.price) > 0
        }

        candidates = []
        for share in shares:
            key = str(getattr(share, "uid", "") or getattr(share, "figi", ""))
            current = last_prices.get(key)
            previous_close = close_prices.get(key)
            if current is None or previous_close is None:
                continue
            candidates.append((
                current / previous_close - 1.0,
                str(getattr(share, "ticker", "") or ""),
                share,
            ))

        candidates.sort(key=lambda item: (-item[0], item[1]))
        selected_10 = [item[2] for item in candidates[:self.max_analysis_instruments]]

        selected_ids = {
            str(getattr(share, "uid", "") or getattr(share, "figi", ""))
            for share in selected_10
        }
        required_tickers = held_tickers | tracked_tickers
        required_shares = [
            share for share in shares
            if str(getattr(share, "ticker", "") or "") in required_tickers
        ]
        analysis_shares = list(selected_10)
        for share in required_shares:
            key = str(getattr(share, "uid", "") or getattr(share, "figi", ""))
            if key not in selected_ids:
                analysis_shares.append(share)

        histories = {}
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.history_days)

        for share in analysis_shares:
            instrument_id = str(
                getattr(share, "uid", "") or getattr(share, "figi", "")
            )
            response = self._get_candles_with_retry(
                instrument_id=instrument_id,
                start=start,
                end=end,
            )
            if response is None:
                continue
            histories[instrument_id] = list(response.candles)

        analyses = {}
        for share in analysis_shares:
            instrument_id = str(
                getattr(share, "uid", "") or getattr(share, "figi", "")
            )
            ticker = str(getattr(share, "ticker", "") or "")
            try:
                analyses[ticker] = self.analyzer.analyze(
                    instrument_id, ticker, histories[instrument_id]
                )
            except ValueError:
                continue

        ranked_selected = [
            analyses[ticker]
            for share in selected_10
            for ticker in [str(getattr(share, "ticker", "") or "")]
            if ticker in analyses
        ]
        ranked_selected.sort(
            key=lambda item: (
                -item.score, -item.momentum, item.volatility, item.ticker
            )
        )

        lot_sizes = {}
        for share in analysis_shares:
            ticker = str(getattr(share, "ticker", "") or "")
            key = str(getattr(share, "uid", "") or getattr(share, "figi", ""))
            raw_lot = getattr(share, "lot", None)
            # Do not invent a one-share lot when instrument metadata is missing.
            # Position sizing must treat unknown lot size as unavailable.
            if (
                ticker
                and key in last_prices
                and isinstance(raw_lot, int)
                and not isinstance(raw_lot, bool)
                and raw_lot > 0
            ):
                lot_sizes[ticker] = raw_lot

        # Candle/history requests can age the initial quote snapshot. Refresh
        # every analyzed instrument (including held/tracked positions) before
        # final eligibility is computed. Invalid or stale refreshes are rejected.
        refresh_instrument_ids = sorted({
            str(getattr(share, "uid", "") or getattr(share, "figi", ""))
            for share in analysis_shares
            if str(getattr(share, "uid", "") or getattr(share, "figi", ""))
        })
        if refresh_instrument_ids:
            try:
                refreshed_count, returned_count = self._refresh_latest_quotes(
                    refresh_instrument_ids,
                    last_prices=last_prices,
                    last_price_items=last_price_items,
                )
                print(
                    f"Post-analysis quote refresh: requested={len(refresh_instrument_ids)} "
                    f"returned={returned_count} accepted_newer_fresh_quotes={refreshed_count}"
                )
            except Exception as exc:
                # The final freshness check below fails closed if refresh fails.
                print(
                    "Post-analysis quote refresh failed; validating cached timestamps: "
                    f"{type(exc).__name__}: {exc}"
                )

        liquidity_by_ticker = {}
        liquidity_spread_ticks_by_ticker = {}
        active_instrument_ids = set()
        trading_status_by_id = {}
        trading_api_available_by_id = {}
        quote_age_by_id = {}
        fresh_quote_ids = set()
        now_utc = datetime.now(timezone.utc)
        try:
            status_response = self.client.market_data.get_trading_statuses(
                instrument_ids=[
                    str(getattr(share, "uid", "") or getattr(share, "figi", ""))
                    for share in analysis_shares
                    if str(getattr(share, "uid", "") or getattr(share, "figi", ""))
                ],
            )
            for item in getattr(status_response, "trading_statuses", ()) or ():
                raw_status = getattr(item, "trading_status", "")
                status_name = str(getattr(raw_status, "name", raw_status)).upper()
                instrument_key = self._instrument_key(item)
                trading_status_by_id[instrument_key] = status_name
                trading_api_available_by_id[instrument_key] = bool(
                    getattr(item, "api_trade_available_flag", False)
                )
        except Exception as exc:
            print(f"GetTradingStatuses failed; order-book liquidity remains unavailable: {exc}")

        # Resolve the returned official schedule against Moscow's current date
        # and UTC clock. Individual instruments inherit only their own exchange.
        exchange_sessions = {}
        for share in shares:
            exchange = str(getattr(share, "exchange", "") or "")
            exchange_key = normalize_exchange(exchange)
            if exchange_key not in exchange_sessions:
                exchange_sessions[exchange_key] = resolve_exchange_session(
                    exchange,
                    schedule_map.get(exchange_key),
                    now_utc,
                )

        session_by_ticker = {}
        for share in analysis_shares:
            ticker = str(getattr(share, "ticker", "") or "")
            instrument_id = str(getattr(share, "uid", "") or getattr(share, "figi", ""))
            exchange = str(getattr(share, "exchange", "") or "")
            exchange_session = exchange_sessions.get(normalize_exchange(exchange))
            status_name = trading_status_by_id.get(instrument_id, "UNAVAILABLE")
            status_compatible = self._status_allows_scheduled_session(
                status_name, exchange_session
            )
            if instrument_id and status_compatible:
                active_instrument_ids.add(instrument_id)
            session_by_ticker[ticker] = {
                **(exchange_session.to_dict() if exchange_session is not None else {}),
                "instrument_exchange": exchange,
                "instrument_uid": str(getattr(share, "uid", "") or ""),
                "figi": str(getattr(share, "figi", "") or ""),
                "weekend_flag": bool(getattr(share, "weekend_flag", False)),
                "trading_status": status_name,
                "broker_status_allows_session": status_compatible,
                "quote_fresh": False,
                "trade_eligible": False,
            }

        # Expose broker status and source quote timestamp so a smoke run can
        # distinguish a fresh active-session quote from an old positive price.
        # This is diagnostic only and does not change trade decisions.
        for share in analysis_shares:
            ticker = str(getattr(share, "ticker", "") or "")
            instrument_id = str(getattr(share, "uid", "") or getattr(share, "figi", ""))
            price_item = last_price_items.get(instrument_id)
            quote_time = getattr(price_item, "time", None) if price_item is not None else None
            quote_age = None
            quote_reason = "fresh"
            if not isinstance(quote_time, datetime):
                quote_reason = "missing_quote_timestamp"
            else:
                quote_age, quote_reason = self._quote_freshness(
                    quote_time, now_utc, self.max_quote_age_seconds
                )
                quote_age_by_id[instrument_id] = quote_age
                if quote_reason == "fresh":
                    fresh_quote_ids.add(instrument_id)
            status_name = trading_status_by_id.get(instrument_id, "UNAVAILABLE")
            api_trade_available = trading_api_available_by_id.get(instrument_id, False)
            quote_price = last_prices.get(instrument_id)
            quote_fresh = instrument_id in fresh_quote_ids
            status_compatible = instrument_id in active_instrument_ids
            ticker_context = session_by_ticker.get(ticker, {})
            ticker_context["api_trade_available_flag"] = api_trade_available
            ticker_context["quote_fresh"] = quote_fresh
            ticker_context["trade_eligible"] = self._instrument_trade_eligible(
                api_trade_available, status_name,
                exchange_sessions.get(normalize_exchange(getattr(share, "exchange", ""))),
                quote_fresh,
            )
            # Keep the specific quote-data rejection reason visible in diagnostics.
            if quote_reason == "fresh":
                if not api_trade_available:
                    quote_reason = "api_trade_unavailable"
                elif not status_compatible:
                    quote_reason = "schedule_closed_or_status_incompatible"
            print(
                f"T-Invest provenance: {ticker or instrument_id} "
                f"instrument_uid={ticker_context.get('instrument_uid', 'UNAVAILABLE')} "
                f"figi={ticker_context.get('figi', 'UNAVAILABLE')} "
                f"exchange={ticker_context.get('instrument_exchange', 'UNAVAILABLE')} "
                f"session={ticker_context.get('session', 'unknown')} "
                f"session_phase={ticker_context.get('phase', 'unknown')} "
                f"schedule_verified={ticker_context.get('verified', False)} "
                f"trading_status={status_name} "
                f"api_trade_available={api_trade_available} "
                f"broker_status_allows_session={status_compatible} "
                f"last_price_time={quote_time.isoformat() if isinstance(quote_time, datetime) else 'UNAVAILABLE'} "
                f"quote_age_seconds={round(quote_age, 1) if quote_age is not None else 'UNAVAILABLE'} "
                f"max_quote_age_seconds={self.max_quote_age_seconds:g} "
                f"last_price={quote_price if quote_price is not None else 'UNAVAILABLE'} "
                f"trade_eligible={ticker_context['trade_eligible']} "
                f"quote_rejection={quote_reason}"
            )

        # Build eligibility sets only after every quote timestamp has been
        # checked and fresh_quote_ids is complete.
        market_context = build_market_context(
            cycle_utc,
            trading_status_by_id,
            status_check_succeeded=bool(trading_status_by_id),
            exchange_sessions=exchange_sessions,
            schedule_check_succeeded=schedule_fetch_succeeded,
        )
        print(
            f"Verified market context: session={market_context.session} "
            f"phase={market_context.session_phase} "
            f"broker_active={market_context.broker_active_instruments}/"
            f"{market_context.broker_reported_instruments} "
            f"broker_status_verified={market_context.broker_status_verified} "
            f"schedule_verified={market_context.schedule_verified} "
            f"next_transition={market_context.next_transition or 'UNAVAILABLE'}"
        )

        active_trading_tickers = {
            str(getattr(share, "ticker", "") or "")
            for share in analysis_shares
            if str(getattr(share, "ticker", "") or "")
            and str(getattr(share, "uid", "") or getattr(share, "figi", "")) in active_instrument_ids
            and self._instrument_trade_eligible(
                trading_api_available_by_id.get(
                    str(getattr(share, "uid", "") or getattr(share, "figi", "")),
                    False,
                ),
                trading_status_by_id.get(
                    str(getattr(share, "uid", "") or getattr(share, "figi", "")),
                    "UNAVAILABLE",
                ),
                exchange_sessions.get(normalize_exchange(getattr(share, "exchange", ""))),
                str(getattr(share, "uid", "") or getattr(share, "figi", "")) in fresh_quote_ids,
            )
        }
        fresh_quote_tickers = {
            str(getattr(share, "ticker", "") or "")
            for share in analysis_shares
            if str(getattr(share, "ticker", "") or "")
            and str(getattr(share, "uid", "") or getattr(share, "figi", "")) in fresh_quote_ids
        }
        print(
            f"T-Invest active trading instruments: "
            f"{len(active_trading_tickers)}/{len(analysis_shares)} analyzed instruments"
        )
        verified_sessions = [
            item for item in exchange_sessions.values() if item.verified
        ]
        open_sessions = [item for item in verified_sessions if item.is_open]
        closed_sessions = [item for item in verified_sessions if not item.is_open]
        unknown_sessions = len(exchange_sessions) - len(verified_sessions)
        phases = sorted({item.phase for item in open_sessions})
        print(
            "Trading readiness summary: "
            f"moscow_date={cycle_moscow.date().isoformat()} "
            f"moscow_weekday={cycle_moscow.strftime('%A')} "
            f"moscow_time={cycle_moscow.strftime('%H:%M:%S')} "
            f"exchange_sessions_open={len(open_sessions)} "
            f"exchange_sessions_closed={len(closed_sessions)} "
            f"exchange_sessions_unknown={unknown_sessions} "
            f"open_phases={','.join(phases) if phases else 'none'} "
            f"trade_eligible_instruments={len(active_trading_tickers)} "
            f"fresh_quotes={len(fresh_quote_tickers)} "
            f"policy=live_api_flag+exchange_schedule+broker_status+fresh_quote"
        )
        if unknown_sessions:
            print(
                "Trading readiness interpretation: some exchange schedules are "
                "unknown; unknown schedules never authorize a new virtual trade."
            )
        elif open_sessions:
            print(
                "Trading readiness interpretation: at least one specific exchange "
                "session is open. This does not mean all instruments are tradable; "
                "use per-instrument trade_eligible and quote provenance."
            )
        else:
            print(
                "Trading readiness interpretation: no verified exchange session "
                "is open; no instrument is eligible for a new virtual trade."
            )

        for share in analysis_shares:
            ticker = str(getattr(share, "ticker", "") or "")
            instrument_id = str(getattr(share, "uid", "") or getattr(share, "figi", ""))
            tick_size_raw = getattr(share, "min_price_increment", None)
            try:
                tick_size = self._quotation(tick_size_raw) if tick_size_raw is not None else None
            except (TypeError, ValueError, OverflowError):
                tick_size = None
            # GetOrderBook has no reliable observation timestamp. Only use it
            # when T-Invest reports an active trading phase; otherwise a stale
            # book from a prior session must not be presented as current liquidity.
            if (
                not ticker
                or not instrument_id
                or instrument_id not in active_instrument_ids
                or tick_size is None
                or tick_size <= 0
            ):
                continue
            try:
                order_book = self.client.market_data.get_order_book(
                    instrument_id=instrument_id,
                    depth=10,
                )
            except Exception as exc:
                print(f"GetOrderBook failed for {ticker}; liquidity remains unavailable: {exc}")
                continue
            bids = getattr(order_book, "bids", ()) or ()
            asks = getattr(order_book, "asks", ()) or ()
            if not bids or not asks:
                continue
            try:
                best_bid = self._quotation(getattr(bids[0], "price", None))
                best_ask = self._quotation(getattr(asks[0], "price", None))
            except (TypeError, ValueError, OverflowError):
                continue
            if (
                not math.isfinite(best_bid)
                or not math.isfinite(best_ask)
                or best_bid <= 0
                or best_ask <= 0
                or best_ask < best_bid
            ):
                continue
            spread_ticks = (best_ask - best_bid) / tick_size
            if not math.isfinite(spread_ticks) or spread_ticks < 0:
                continue
            # This is explicitly a top-of-book spread proxy, not a claim about
            # total market depth. It is derived only from observed T-Invest data.
            normalized_spread_ticks = max(1.0, float(spread_ticks))
            liquidity_by_ticker[ticker] = max(0.0, min(1.0, 1.0 / normalized_spread_ticks))
            liquidity_spread_ticks_by_ticker[ticker] = float(spread_ticks)

        previous_closes = {}
        for share in shares:
            ticker = str(getattr(share, "ticker", "") or "")
            key = str(getattr(share, "uid", "") or getattr(share, "figi", ""))
            if ticker and key in close_prices:
                previous_closes[ticker] = close_prices[key]

        current_prices = {}
        for share in shares:
            ticker = str(getattr(share, "ticker", "") or "")
            key = str(getattr(share, "uid", "") or getattr(share, "figi", ""))
            # Do not pass stale, timestamp-less, or future-dated quotes to
            # valuation or execution as if they were current market prices.
            if ticker and key in last_prices and key in fresh_quote_ids:
                current_prices[ticker] = last_prices[key]

        latest_candles = {}
        candle_history = {}
        for share in analysis_shares:
            ticker = str(getattr(share, "ticker", "") or "")
            key = str(getattr(share, "uid", "") or getattr(share, "figi", ""))
            candles = histories.get(key, ())
            if ticker and candles:
                latest_candles[ticker] = candles[-1]
                candle_history[ticker] = list(candles)

        ticker_changes = {
            ticker: current / previous - 1.0
            for ticker, current in current_prices.items()
            if current > 0 and (previous := previous_closes.get(ticker)) is not None and previous > 0
        }
        sector_by_ticker = {}
        sector_groups = {}
        for share in shares:
            ticker = str(getattr(share, "ticker", "") or "")
            raw_sector = getattr(share, "sector", None)
            sector = str(getattr(raw_sector, "name", raw_sector) or "").strip()
            if "." in sector:
                sector = sector.rsplit(".", 1)[-1]
            if ticker and sector and sector.lower() not in {"none", "unknown", "instrument_sector_unspecified"}:
                sector_by_ticker[ticker] = sector
                if ticker in ticker_changes:
                    sector_groups.setdefault(sector, []).append(ticker_changes[ticker])
        sector_returns = {
            sector: sum(changes) / len(changes)
            for sector, changes in sector_groups.items() if changes
        }
        market_changes = list(ticker_changes.values())
        market_return = sum(market_changes) / len(market_changes) if market_changes else None
        market_breadth = (
            sum(change > 0 for change in market_changes) / len(market_changes)
            if market_changes else None
        )

        return LiveScanResult(
            selected_10=selected_10,
            selected_3=ranked_selected[:3],
            buy_candidates=ranked_selected,
            analyses=analyses,
            current_prices=current_prices,
            previous_closes=previous_closes,
            lot_sizes=lot_sizes,
            active_trading_tickers=active_trading_tickers,
            fresh_quote_tickers=fresh_quote_tickers,
            liquidity_by_ticker=liquidity_by_ticker,
            liquidity_spread_ticks_by_ticker=liquidity_spread_ticks_by_ticker,
            latest_candles=latest_candles,
            candle_history=candle_history,
            sector_by_ticker=sector_by_ticker,
            sector_returns=sector_returns,
            market_return=market_return,
            market_breadth=market_breadth,
            market_sample_count=len(market_changes),
            market_context=market_context,
            session_by_ticker=session_by_ticker,
        )

    def _get_candles_with_retry(
        self,
        instrument_id: str,
        start: datetime,
        end: datetime,
        attempts: int = 3,
    ):
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                return self.client.market_data.get_candles(
                    instrument_id=instrument_id,
                    from_=start,
                    to=end,
                    interval=self._daily_interval(),
                )
            except Exception as exc:
                last_error = exc
                print(
                    f"GetCandles failed for {instrument_id} "
                    f"(attempt {attempt}/{attempts}): {exc}"
                )
                if attempt < attempts:
                    time.sleep(1.0 * attempt)

        print(
            f"Skipping {instrument_id} after {attempts} failed "
            f"GetCandles attempts: {last_error}"
        )
        return None


    def _load_trading_schedules(self, now_utc: datetime) -> tuple[dict[str, object], bool]:
        """Fetch all current/future exchange schedules once, with a short cache."""
        if (
            self._schedule_cache_at is not None
            and self._schedule_cache
            and (now_utc - self._schedule_cache_at).total_seconds() < self.schedule_cache_ttl_seconds
        ):
            return self._schedule_cache, True
        try:
            response = self.client.instruments.trading_schedules(
                exchange="",
                from_=now_utc,
                to=now_utc + timedelta(days=6, hours=23, minutes=59),
            )
            schedules = getattr(response, "exchanges", ()) or ()
            cache = {
                normalize_exchange(getattr(item, "exchange", "")): item
                for item in schedules
                if normalize_exchange(getattr(item, "exchange", ""))
            }
            if not cache:
                raise RuntimeError("TradingSchedules returned no exchange calendars")
            self._schedule_cache = cache
            self._schedule_cache_at = now_utc
            return cache, True
        except Exception as exc:
            print(f"TradingSchedules failed; fail-closed for new virtual trades: {type(exc).__name__}: {exc}")
            return {}, False

    @classmethod
    def _status_allows_scheduled_session(
        cls,
        status_name: str,
        exchange_session: ExchangeSession | None,
    ) -> bool:
        """Require a verified open session for this instrument's own exchange."""
        if exchange_session is None or not exchange_session.verified or not exchange_session.is_open:
            return False
        normalized = str(status_name or "").upper()
        if normalized in {
            "SECURITY_TRADING_STATUS_DEALER_NORMAL_TRADING",
            "DEALER_NORMAL_TRADING",
        }:
            # Dealer weekend/extended sessions are accepted only when the
            # instrument's declared exchange schedule explicitly reports open.
            return True
        return cls._is_active_trading_status(normalized)

    @classmethod
    def _instrument_trade_eligible(
        cls,
        api_trade_available_flag: object,
        status_name: str,
        exchange_session: ExchangeSession | None,
        quote_fresh: bool,
    ) -> bool:
        """Require every independent broker/session/quote gate for trading."""
        return bool(
            api_trade_available_flag
            and quote_fresh
            and cls._status_allows_scheduled_session(status_name, exchange_session)
        )

    @staticmethod
    def _is_tradable_rub_share(share: object) -> bool:
        currency = str(getattr(share, "currency", "") or "").upper()
        return (
            currency in {"RUB", "RUR"}
            and bool(getattr(share, "api_trade_available_flag", True))
        )

    @staticmethod
    def _instrument_key(item: object) -> str:
        return str(
            getattr(item, "instrument_uid", "")
            or getattr(item, "figi", "")
            or ""
        )

    def _refresh_latest_quotes(
        self,
        instrument_ids: list[str],
        *,
        last_prices: dict[str, float],
        last_price_items: dict[str, object],
        now: datetime | None = None,
    ) -> tuple[int, int]:
        """Refresh instruments and merge only newer, positive, fresh quotes."""
        requested_ids = sorted({str(value) for value in instrument_ids if str(value)})
        if not requested_ids:
            return 0, 0
        response = self.client.market_data.get_last_prices(instrument_id=requested_ids)
        refresh_now = now or datetime.now(timezone.utc)
        returned_by_id = {
            self._instrument_key(item): item
            for item in (getattr(response, "last_prices", ()) or ())
            if self._instrument_key(item)
        }
        accepted_count = 0
        for instrument_id in requested_ids:
            item = returned_by_id.get(instrument_id)
            if item is None:
                print(f"Post-analysis quote refresh detail: instrument_id={instrument_id} result=not_returned")
                continue
            quote_time = getattr(item, "time", None)
            try:
                price = self._quotation(getattr(item, "price", 0))
            except (TypeError, ValueError, OverflowError):
                price = "UNAVAILABLE"
            age = None
            reason = "missing_quote_timestamp"
            if isinstance(quote_time, datetime):
                age, reason = self._quote_freshness(quote_time, refresh_now, self.max_quote_age_seconds)
            accepted = self._merge_fresh_newer_quote(
                item,
                last_prices=last_prices,
                last_price_items=last_price_items,
                now=refresh_now,
                max_age_seconds=self.max_quote_age_seconds,
            )
            accepted_count += int(accepted)
            print(
                f"Post-analysis quote refresh detail: instrument_id={instrument_id} "
                f"price={price} quote_time={quote_time.isoformat() if isinstance(quote_time, datetime) else 'UNAVAILABLE'} "
                f"quote_age_seconds={round(age, 1) if age is not None else 'UNAVAILABLE'} "
                f"freshness={reason} accepted_newer_fresh_quote={accepted}"
            )
        return accepted_count, len(returned_by_id)

    @classmethod
    def _merge_fresh_newer_quote(
        cls,
        item: object,
        *,
        last_prices: dict[str, float],
        last_price_items: dict[str, object],
        now: datetime,
        max_age_seconds: float,
    ) -> bool:
        """Replace a cached quote only with a newer, positive, fresh broker quote."""
        instrument_id = cls._instrument_key(item)
        if not instrument_id:
            return False
        try:
            price = cls._quotation(getattr(item, "price", None))
        except (TypeError, ValueError, OverflowError):
            return False
        quote_time = getattr(item, "time", None)
        if (
            not math.isfinite(price)
            or price <= 0
            or not isinstance(quote_time, datetime)
            or cls._quote_freshness(quote_time, now, max_age_seconds)[1] != "fresh"
        ):
            return False

        previous_item = last_price_items.get(instrument_id)
        previous_time = getattr(previous_item, "time", None) if previous_item is not None else None
        if isinstance(previous_time, datetime):
            old_time = previous_time if previous_time.tzinfo else previous_time.replace(tzinfo=timezone.utc)
            new_time = quote_time if quote_time.tzinfo else quote_time.replace(tzinfo=timezone.utc)
            _, previous_reason = cls._quote_freshness(previous_time, now, max_age_seconds)
            # A valid fresh timestamp may replace an older fresh/stale timestamp.
            # An invalid future-dated cached timestamp must not block a valid quote.
            if (
                previous_reason != "quote_timestamp_in_future"
                and new_time.astimezone(timezone.utc) <= old_time.astimezone(timezone.utc)
            ):
                return False

        last_prices[instrument_id] = price
        last_price_items[instrument_id] = item
        return True

    @staticmethod
    def _quotation(value: object) -> float:
        units = getattr(value, "units", None)
        nano = getattr(value, "nano", None)
        if units is None:
            return float(value)
        return float(units) + float(nano or 0) / 1_000_000_000

    @staticmethod
    def _is_active_trading_status(status_name: str) -> bool:
        """Accept only explicit exchange trading phases, never substring matches."""
        return str(status_name).upper() in {
            "SECURITY_TRADING_STATUS_NORMAL_TRADING",
            "SECURITY_TRADING_STATUS_OPENING_PERIOD",
            "SECURITY_TRADING_STATUS_CLOSING_PERIOD",
            "NORMAL_TRADING",
            "OPENING_PERIOD",
            "CLOSING_PERIOD",
        }

    @staticmethod
    def _quote_freshness(
        quote_time: datetime,
        now: datetime,
        max_age_seconds: float,
    ) -> tuple[float, str]:
        """Return age and rejection reason for a source quote timestamp."""
        if quote_time.tzinfo is None:
            quote_time = quote_time.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        age = (now.astimezone(timezone.utc) - quote_time.astimezone(timezone.utc)).total_seconds()
        if age < -60:
            return age, "quote_timestamp_in_future"
        if age > max_age_seconds:
            return age, "stale_quote"
        # Tolerate small clock skew, but never trade on a quote older than the limit.
        return age, "fresh"

    @staticmethod
    def _positive_env_float(name: str, default: float) -> float:
        import os

        raw = os.getenv(name, str(default)).strip()
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(f"{name} must be a positive number") from exc
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be a positive finite number")
        return value

    @staticmethod
    def _positive_env_int(name: str, default: int) -> int:
        import os

        raw = os.getenv(name, str(default)).strip()
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError(f"{name} must be a positive integer") from exc
        if value <= 0:
            raise ValueError(f"{name} must be a positive integer")
        return value

    @staticmethod
    def _daily_interval():
        from t_tech.invest import CandleInterval
        return CandleInterval.CANDLE_INTERVAL_DAY