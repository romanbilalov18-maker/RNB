from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import time
import math

from bot.stock_analysis import StockAnalysis, StockAnalyzer


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


class LiveMarketRunner:
    """Run one real-market analysis cycle using T-Invest market data only."""

    def __init__(self, client, history_days: int = 30):
        if history_days <= 0:
            raise ValueError("history_days must be positive")
        self.client = client
        self.history_days = history_days
        self.analyzer = StockAnalyzer(min_history=20, momentum_period=10)
        self.max_quote_age_seconds = self._positive_env_float(
            "TINVEST_MAX_QUOTE_AGE_SECONDS", 300.0
        )
        # Analyze a wider real-market shortlist by default. Keep configurable
        # because historical-candle requests are rate-limited by the broker.
        self.max_analysis_instruments = self._positive_env_int(
            "TINVEST_MAX_ANALYSIS_INSTRUMENTS", 50
        )

    def run(
        self,
        held_tickers: set[str] | None = None,
        tracked_tickers: set[str] | None = None,
    ) -> LiveScanResult:
        held_tickers = held_tickers or set()
        tracked_tickers = tracked_tickers or set()

        shares_response = self.client.instruments.shares()
        shares = [
            share for share in shares_response.instruments
            if self._is_tradable_rub_share(share)
        ]
        if not shares:
            raise RuntimeError("T-Invest returned no tradable RUB shares")

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

        liquidity_by_ticker = {}
        liquidity_spread_ticks_by_ticker = {}
        active_instrument_ids = set()
        trading_status_by_id = {}
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
                trading_status_by_id[self._instrument_key(item)] = status_name
                # Only exchange-session statuses authorize trading. In particular,
                # DEALER_NORMAL_TRADING is not equivalent to NORMAL_TRADING.
                if self._is_active_trading_status(status_name):
                    active_instrument_ids.add(self._instrument_key(item))
        except Exception as exc:
            print(f"GetTradingStatuses failed; order-book liquidity remains unavailable: {exc}")

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
            quote_price = last_prices.get(instrument_id)
            if instrument_id not in active_instrument_ids:
                quote_reason = "inactive_or_unconfirmed_trading_status"
            elif instrument_id not in fresh_quote_ids:
                # Keep the more specific stale/missing/future timestamp reason.
                if quote_reason == "fresh":
                    quote_reason = "quote_not_verified_fresh"
            print(
                f"T-Invest provenance: {ticker or instrument_id} "
                f"trading_status={status_name} "
                f"last_price_time={quote_time.isoformat() if isinstance(quote_time, datetime) else 'UNAVAILABLE'} "
                f"quote_age_seconds={round(quote_age, 1) if quote_age is not None else 'UNAVAILABLE'} "
                f"max_quote_age_seconds={self.max_quote_age_seconds:g} "
                f"last_price={quote_price if quote_price is not None else 'UNAVAILABLE'} "
                f"trade_eligible={instrument_id in active_instrument_ids and instrument_id in fresh_quote_ids} "
                f"quote_rejection={quote_reason}"
            )

        # Build eligibility sets only after every quote timestamp has been
        # checked and fresh_quote_ids is complete.
        active_trading_tickers = {
            str(getattr(share, "ticker", "") or "")
            for share in analysis_shares
            if str(getattr(share, "ticker", "") or "")
            and str(getattr(share, "uid", "") or getattr(share, "figi", "")) in active_instrument_ids
            and str(getattr(share, "uid", "") or getattr(share, "figi", "")) in fresh_quote_ids
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
