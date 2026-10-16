import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


def _finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def analyze(snapshot: MarketSnapshot, level2: Level2Result) -> AnalyzerResult:
    """Use observed broad-market breadth/returns; never fabricate macro indicators."""
    breadth = snapshot.market_breadth
    sample_count = snapshot.market_sample_count
    market_return = snapshot.market_return

    if (
        not _finite_number(breadth)
        or not 0.0 <= breadth <= 1.0
        or isinstance(sample_count, bool)
        or not isinstance(sample_count, int)
        or sample_count < 10
    ):
        return AnalyzerResult(
            "macro_context", 0.0, 0.0,
            {
                "available": False,
                "market_sample_count": sample_count,
                "market_breadth": breadth,
            },
            ("market_breadth_insufficient_or_invalid", "macro_indicators_not_provided"),
        )

    valid_return = _finite_number(market_return)
    return_score = max(0.0, min(1.0, 0.5 + market_return * 8.0)) if valid_return else None
    score = 0.65 * breadth + 0.35 * return_score if return_score is not None else breadth
    confidence = min(1.0, sample_count / 100.0) * (1.0 if return_score is not None else 0.5)
    warnings = () if valid_return else ("market_return_unavailable_or_invalid",)
    return AnalyzerResult(
        "macro_context", score, confidence,
        {
            "context_type": "observed_market_breadth",
            "market_breadth": breadth,
            "market_return": market_return if valid_return else None,
            "sample_count": sample_count,
            "official_macro_indicators_available": False,
        },
        (*warnings, "macro_indicators_not_provided"),
    )
