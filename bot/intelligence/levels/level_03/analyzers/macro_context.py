from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


def analyze(snapshot: MarketSnapshot, level2: Level2Result) -> AnalyzerResult:
    """Use actual broad-market breadth/returns; never fabricate macro indicators."""
    if snapshot.market_breadth is None or snapshot.market_sample_count < 10:
        return AnalyzerResult(
            "macro_context", 0.0, 0.0,
            {"available": False, "market_sample_count": snapshot.market_sample_count},
            ("market_breadth_insufficient", "macro_indicators_not_provided"),
        )
    breadth = max(0.0, min(1.0, snapshot.market_breadth))
    market_return = snapshot.market_return
    return_score = 0.5 if market_return is None else max(0.0, min(1.0, 0.5 + market_return * 8.0))
    score = 0.65 * breadth + 0.35 * return_score
    confidence = min(1.0, snapshot.market_sample_count / 100.0)
    return AnalyzerResult(
        "macro_context", score, confidence,
        {"context_type": "observed_market_breadth", "market_breadth": breadth,
         "market_return": market_return, "sample_count": snapshot.market_sample_count,
         "official_macro_indicators_available": False},
        ("macro_indicators_not_provided",),
    )
