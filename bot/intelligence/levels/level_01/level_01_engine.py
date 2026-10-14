from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from .analyzers import data_quality, liquidity, momentum, price, volatility, volume


ANALYZERS = (price, volume, volatility, momentum, liquidity, data_quality)


def analyze(snapshot: MarketSnapshot) -> tuple[AnalyzerResult, ...]:
    """Run every Level 1 analyzer without mutating the snapshot or bot state."""
    return tuple(module.analyze(snapshot) for module in ANALYZERS)


def aggregate(results: tuple[AnalyzerResult, ...]) -> float:
    """Average only analyzers backed by available source data."""
    observed = [result for result in results if result.confidence > 0]
    if not observed:
        return 0.0
    return sum(result.score * result.confidence for result in observed) / sum(result.confidence for result in observed)
