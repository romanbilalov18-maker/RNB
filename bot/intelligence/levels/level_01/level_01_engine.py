from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from .analyzers import data_quality, liquidity, momentum, price, volatility, volume


ANALYZERS = (price, volume, volatility, momentum, liquidity, data_quality)
# Directional attractiveness (alpha) and execution/risk constraints are separate.
ALPHA_ANALYZERS = frozenset({"price", "momentum", "volume"})
RISK_ANALYZERS = frozenset({"volatility", "liquidity"})


def analyze(snapshot: MarketSnapshot) -> tuple[AnalyzerResult, ...]:
    """Run every Level 1 analyzer without mutating the snapshot or bot state."""
    return tuple(module.analyze(snapshot) for module in ANALYZERS)


def alpha_results(results: tuple[AnalyzerResult, ...]) -> tuple[AnalyzerResult, ...]:
    """Return only observed directional inputs; risk and data-quality stay separate."""
    return tuple(
        result for result in results
        if result.analyzer in ALPHA_ANALYZERS and result.confidence > 0
    )


def risk_results(results: tuple[AnalyzerResult, ...]) -> tuple[AnalyzerResult, ...]:
    """Return observed risk/execution diagnostics without blending them into alpha."""
    return tuple(
        result for result in results
        if result.analyzer in RISK_ANALYZERS and result.confidence > 0
    )


def aggregate(results: tuple[AnalyzerResult, ...]) -> float:
    """Confidence-weighted attractiveness score from price, momentum and volume only."""
    observed = alpha_results(results)
    if not observed:
        return 0.0
    return sum(result.score * result.confidence for result in observed) / sum(
        result.confidence for result in observed
    )
