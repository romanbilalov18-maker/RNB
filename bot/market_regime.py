from dataclasses import dataclass
from enum import Enum
from math import sqrt

from bot.dataset import Dataset
from bot.models import DecisionContext


class MarketRegime(str, Enum):
    TREND = "TREND"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"


@dataclass(frozen=True)
class RegimeResult:
    regime: MarketRegime
    volatility: float
    trend_strength: float
    confidence: float


class MarketRegimeEngine:
    def __init__(
        self,
        volatility_period: int = 20,
        trend_period: int = 20,
        high_volatility_threshold: float = 0.02,
        low_volatility_threshold: float = 0.005,
        trend_threshold: float = 0.01,
    ) -> None:
        if volatility_period <= 1 or trend_period <= 1:
            raise ValueError("periods must be greater than 1")
        if not 0 <= low_volatility_threshold < high_volatility_threshold:
            raise ValueError("volatility thresholds must satisfy 0 <= low < high")
        if trend_threshold <= 0:
            raise ValueError("trend_threshold must be positive")
        self.volatility_period = volatility_period
        self.trend_period = trend_period
        self.high_volatility_threshold = high_volatility_threshold
        self.low_volatility_threshold = low_volatility_threshold
        self.trend_threshold = trend_threshold

    def classify_context(self, context: DecisionContext) -> RegimeResult:
        if not context.candles:
            raise ValueError("decision context must contain historical candles")
        return self.classify_closes(context.closes)

    def classify_closes(self, closes: list[float] | tuple[float, ...]) -> RegimeResult:
        if not closes:
            raise ValueError("closes must not be empty")
        if any(price <= 0 for price in closes):
            raise ValueError("closes must be positive")

        volatility = _volatility(closes, self.volatility_period)
        trend_strength = _trend_strength(closes, self.trend_period)

        trend_to_volatility = _trend_to_volatility_ratio(
            trend_strength, volatility, self.trend_period
        )

        if volatility >= self.high_volatility_threshold:
            regime = MarketRegime.HIGH_VOLATILITY
        elif (
            trend_strength >= self.trend_threshold
            or trend_to_volatility >= 0.75
        ):
            regime = MarketRegime.TREND
        elif volatility <= self.low_volatility_threshold:
            regime = MarketRegime.LOW_VOLATILITY
        else:
            regime = MarketRegime.RANGE

        confidence = _confidence(
            volatility,
            trend_strength,
            self.low_volatility_threshold,
            self.high_volatility_threshold,
            self.trend_threshold,
        )
        return RegimeResult(regime, volatility, trend_strength, confidence)

    def classify(self, dataset: Dataset, index: int | None = None) -> RegimeResult:
        if len(dataset) == 0:
            raise ValueError("dataset must not be empty")
        if index is None:
            index = len(dataset) - 1
        if index < 0 or index >= len(dataset):
            raise IndexError("index out of range")
        closes = [candle.close for candle in dataset.candles[: index + 1]]
        return self.classify_closes(closes)

    def build(self, dataset: Dataset) -> list[RegimeResult | None]:
        warmup = max(self.volatility_period, self.trend_period)
        return [
            None if index < warmup else self.classify(dataset, index)
            for index in range(len(dataset))
        ]


def _volatility(closes, period: int) -> float:
    if len(closes) <= period:
        return 0.0
    returns = [
        closes[i] / closes[i - 1] - 1.0
        for i in range(len(closes) - period, len(closes))
    ]
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    return sqrt(variance)


def _trend_strength(closes, period: int) -> float:
    if len(closes) <= period:
        return 0.0
    return abs(closes[-1] / closes[-period - 1] - 1.0)


def _trend_to_volatility_ratio(trend_strength: float, volatility: float, period: int) -> float:
    if volatility <= 1e-12:
        return float("inf") if trend_strength > 0 else 0.0
    return trend_strength / (volatility * sqrt(period))


def _confidence(volatility, trend_strength, low, high, trend) -> float:
    if volatility <= low:
        volatility_confidence = 1.0 - volatility / max(low, 1e-12)
    elif volatility >= high:
        volatility_confidence = min(1.0, (volatility - high) / max(high - low, 1e-12))
    else:
        volatility_confidence = 1.0 - (volatility - low) / max(high - low, 1e-12)
    trend_confidence = min(1.0, trend_strength / trend)
    return max(0.0, min(1.0, max(volatility_confidence, trend_confidence)))
