import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result


def analyze(snapshot: MarketSnapshot, level1: Level1Result) -> AnalyzerResult:
    """Measure strength against a real benchmark, not liquidity or momentum proxies."""
    relative_return = snapshot.relative_market_return
    sample_count = snapshot.relative_market_sample_count

    if (
        not snapshot.relative_market_context_available
        or isinstance(relative_return, bool)
        or not isinstance(relative_return, (int, float))
        or not math.isfinite(relative_return)
        or isinstance(sample_count, bool)
        or not isinstance(sample_count, int)
        or sample_count <= 0
    ):
        return AnalyzerResult(
            "relative_strength",
            0.0,
            0.0,
            {
                "relative_market_return": relative_return,
                "relative_market_sample_count": sample_count,
                "available_inputs": [],
            },
            ("relative_market_context_unavailable",),
        )

    # Scores express direction of relative performance; the raw return remains
    # available in metrics. Avoid inventing a volatility/scale normalization.
    score = 1.0 if relative_return > 0 else 0.0 if relative_return < 0 else 0.5
    return AnalyzerResult(
        "relative_strength",
        score,
        1.0,
        {
            "relative_market_return": relative_return,
            "relative_market_sample_count": sample_count,
            "available_inputs": ["relative_market_return"],
        },
    )
