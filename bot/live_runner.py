from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import time

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
        selected_10 = [item[2] for item in candidates[:10]]

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
            if ticker and key in last_prices:
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
    def _daily_interval():
        from t_tech.invest import CandleInterval
        return CandleInterval.CANDLE_INTERVAL_DAY
