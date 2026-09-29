from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import mean, pstdev
from typing import Sequence


@dataclass(frozen=True)
class StockAnalysis:
    instrument_id: str
    ticker: str
    last_price: float
    return_period: float
    volatility: float
    momentum: float
    average_volume: float
    volume_ratio: float
    trend_strength: float
    score: float


class StockAnalyzer:
    """Analyze historical OHLCV data and rank stocks for the next decision stage."""

    def __init__(
        self,
        min_history: int = 20,
        momentum_period: int = 10,
    ):
        if min_history < 2:
            raise ValueError("min_history must be at least 2")
        if momentum_period <= 0:
            raise ValueError("momentum_period must be positive")
        if momentum_period >= min_history:
            raise ValueError("momentum_period must be smaller than min_history")

        self.min_history = min_history
        self.momentum_period = momentum_period

    def analyze(
        self,
        instrument_id: str,
        ticker: str,
        candles: Sequence[object],
    ) -> StockAnalysis:
        if len(candles) < self.min_history:
            raise ValueError(
                f"{ticker}: not enough history; "
                f"need {self.min_history}, got {len(candles)}"
            )

        closes = [self._price(candle, "close") for candle in candles]
        volumes = [
            max(0.0, self._price(candle, "volume"))
            for candle in candles
        ]

        if any(price <= 0 for price in closes):
            raise ValueError(f"{ticker}: historical prices must be positive")

        last_price = closes[-1]
        start_price = closes[0]
        return_period = last_price / start_price - 1.0

        momentum_base = closes[-self.momentum_period - 1]
        momentum = last_price / momentum_base - 1.0

        returns = [
            closes[index] / closes[index - 1] - 1.0
            for index in range(1, len(closes))
        ]
        volatility = pstdev(returns) * sqrt(len(returns)) if len(returns) > 1 else 0.0

        average_volume = mean(volumes)
        recent_volume = mean(volumes[-min(5, len(volumes)):])
        volume_ratio = (
            recent_volume / average_volume
            if average_volume > 0
            else 0.0
        )

        trend_strength = self._trend_strength(closes)

        # This is a screening score, not a promise of future profitability.
        score = (
            0.35 * _clamp(momentum / 0.10)
            + 0.25 * _clamp(return_period / 0.20)
            + 0.20 * _clamp((volume_ratio - 1.0) / 1.0)
            + 0.20 * _clamp(trend_strength / 0.10)
        )

        return StockAnalysis(
            instrument_id=instrument_id,
            ticker=ticker,
            last_price=last_price,
            return_period=return_period,
            volatility=volatility,
            momentum=momentum,
            average_volume=average_volume,
            volume_ratio=volume_ratio,
            trend_strength=trend_strength,
            score=score,
        )

    def rank(
        self,
        candidates: Sequence[object],
        history_by_instrument: dict[str, Sequence[object]],
    ) -> list[StockAnalysis]:
        analyses = []

        for candidate in candidates:
            instrument_id = candidate.instrument_id
            history = history_by_instrument.get(instrument_id, ())
            try:
                analysis = self.analyze(
                    instrument_id,
                    candidate.ticker,
                    history,
                )
            except ValueError:
                continue
            analyses.append(analysis)

        analyses.sort(
            key=lambda item: (
                -item.score,
                -item.momentum,
                item.volatility,
                item.ticker,
            )
        )
        return analyses

    @staticmethod
    def _trend_strength(closes: Sequence[float]) -> float:
        if len(closes) < 3:
            return 0.0

        x_mean = (len(closes) - 1) / 2
        y_mean = mean(closes)

        numerator = sum(
            (index - x_mean) * (price - y_mean)
            for index, price in enumerate(closes)
        )
        denominator = sum(
            (index - x_mean) ** 2
            for index in range(len(closes))
        )

        if denominator == 0 or y_mean == 0:
            return 0.0

        slope = numerator / denominator
        return slope / y_mean

    @staticmethod
    def _price(candle: object, field: str) -> float:
        value = getattr(candle, field, None)
        if value is None:
            raise ValueError(f"candle is missing {field}")

        units = getattr(value, "units", None)
        nano = getattr(value, "nano", None)
        if units is not None:
            return float(units) + float(nano or 0) / 1_000_000_000

        return float(value)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
