from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from bot.stock_analysis import StockAnalysis, StockAnalyzer


@dataclass(frozen=True)
class LiveScanResult:
    selected_10: list[object]
    selected_3: list[StockAnalysis]
    analyses: dict[str, StockAnalysis]
    current_prices: dict[str, float]
    lot_sizes: dict[str, int]


class LiveMarketRunner:
    """Run one real-market analysis cycle using T-Invest market data only."""

    def __init__(self, client, history_days: int = 30):
        if history_days <= 0:
            raise ValueError("history_days must be positive")
        self.client = client
        self.history_days = history_days
        self.analyzer = StockAnalyzer(min_history=20, momentum_period=10)

    def run(self, held_tickers: set[str] | None = None) -> LiveScanResult:
        held_tickers = held_tickers or set()

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
        held_shares = [
            share for share in shares
            if str(getattr(share, "ticker", "") or "") in held_tickers
        ]
        analysis_shares = list(selected_10)
        for share in held_shares:
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
            response = self.client.market_data.get_candles(
                instrument_id=instrument_id,
                from_=start,
                to=end,
                interval=self._daily_interval(),
            )
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
            if ticker and key in last_prices:
                lot_sizes[ticker] = int(getattr(share, "lot", 1) or 1)

        current_prices = {}
        for share in shares:
            ticker = str(getattr(share, "ticker", "") or "")
            key = str(getattr(share, "uid", "") or getattr(share, "figi", ""))
            if ticker and key in last_prices:
                current_prices[ticker] = last_prices[key]

        return LiveScanResult(
            selected_10=selected_10,
            selected_3=ranked_selected[:3],
            analyses=analyses,
            current_prices=current_prices,
            lot_sizes=lot_sizes,
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
