from dataclasses import dataclass
from datetime import datetime
from math import sqrt

from bot.dataset import Dataset


@dataclass(frozen=True)
class FeatureVector:
    timestamp: datetime
    close: float
    sma_fast: float | None
    sma_slow: float | None
    ema_fast: float | None
    ema_slow: float | None
    return_1: float | None
    momentum: float | None
    volatility: float | None
    rsi: float | None
    atr: float | None
    volume_ratio: float | None


class FeatureEngine:
    """Build deterministic, point-in-time market features."""

    def __init__(
        self,
        fast_period: int = 5,
        slow_period: int = 20,
        rsi_period: int = 14,
        volatility_period: int = 20,
        momentum_period: int = 10,
        atr_period: int = 14,
        volume_period: int = 20,
    ):
        periods = (
            fast_period, slow_period, rsi_period, volatility_period,
            momentum_period, atr_period, volume_period,
        )
        if any(period <= 0 for period in periods):
            raise ValueError("All feature periods must be positive")
        if fast_period >= slow_period:
            raise ValueError("fast_period must be smaller than slow_period")

        self.fast_period = fast_period
        self.slow_period = slow_period
        self.rsi_period = rsi_period
        self.volatility_period = volatility_period
        self.momentum_period = momentum_period
        self.atr_period = atr_period
        self.volume_period = volume_period

    def build(self, dataset: Dataset) -> list[FeatureVector]:
        return [self.compute(dataset, index) for index in range(len(dataset))]

    def compute(self, dataset: Dataset, index: int) -> FeatureVector:
        if index < 0 or index >= len(dataset):
            raise IndexError("index out of range")

        candles = dataset.candles
        current = candles[index]
        closes = [candle.close for candle in candles[: index + 1]]
        volumes = [candle.volume for candle in candles[: index + 1]]

        return FeatureVector(
            timestamp=current.timestamp,
            close=current.close,
            sma_fast=_sma(closes, self.fast_period),
            sma_slow=_sma(closes, self.slow_period),
            ema_fast=_ema(closes, self.fast_period),
            ema_slow=_ema(closes, self.slow_period),
            return_1=_return(closes, 1),
            momentum=_return(closes, self.momentum_period),
            volatility=_volatility(closes, self.volatility_period),
            rsi=_rsi(closes, self.rsi_period),
            atr=_atr(candles[: index + 1], self.atr_period),
            volume_ratio=_volume_ratio(volumes, self.volume_period),
        )


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    ema = sum(values[:period]) / period
    multiplier = 2 / (period + 1)
    for value in values[period:]:
        ema = (value - ema) * multiplier + ema
    return ema


def _return(values: list[float], period: int) -> float | None:
    if len(values) <= period:
        return None
    previous = values[-period - 1]
    if previous <= 0:
        return None
    return values[-1] / previous - 1.0


def _volatility(values: list[float], period: int) -> float | None:
    if len(values) <= period:
        return None
    returns = [
        values[i] / values[i - 1] - 1.0
        for i in range(len(values) - period, len(values))
        if values[i - 1] > 0
    ]
    if len(returns) < period:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    return sqrt(variance)


def _rsi(values: list[float], period: int) -> float | None:
    if len(values) <= period:
        return None
    changes = [
        values[i] - values[i - 1]
        for i in range(len(values) - period, len(values))
    ]
    gains = sum(max(change, 0.0) for change in changes) / period
    losses = sum(max(-change, 0.0) for change in changes) / period
    if losses == 0:
        return 100.0 if gains > 0 else 50.0
    relative_strength = gains / losses
    return 100.0 - (100.0 / (1.0 + relative_strength))


def _atr(candles, period: int) -> float | None:
    if len(candles) <= period:
        return None
    true_ranges = []
    for index in range(len(candles) - period, len(candles)):
        candle = candles[index]
        previous_close = candles[index - 1].close
        true_ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )
    return sum(true_ranges) / len(true_ranges)


def _volume_ratio(volumes: list[int], period: int) -> float | None:
    if len(volumes) < period:
        return None
    average = sum(volumes[-period:]) / period
    if average <= 0:
        return None
    return volumes[-1] / average
