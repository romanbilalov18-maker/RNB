from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from .analyzers import data_quality, liquidity, momentum, price, volatility, volume


ANALYZERS = (price, volume, volatility, momentum, liquidity, data_quality)


def analyze(snapshot: MarketSnapshot) -> tuple[AnalyzerResult, ...]:
    """Run every Level 1 analyzer without mutating the snapshot or bot state."""
    return tuple(module.analyze(snapshot) for module in ANALYZERS)


def aggregate(results: tuple[AnalyzerResult, ...]) -> float:
    """Produce a neutral average score for Level 1 only."""
    if not results:
        return 0.0
    return sum(result.score for result in results) / len(results)
