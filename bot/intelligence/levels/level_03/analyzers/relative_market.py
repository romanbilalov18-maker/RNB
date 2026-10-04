from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


def analyze(snapshot: MarketSnapshot, level2: Level2Result) -> AnalyzerResult:
    strength = next((r.score for r in level2.analyzer_results if r.analyzer == "relative_strength"), 0.5)
    trend = next((r.score for r in level2.analyzer_results if r.analyzer == "trend"), 0.5)
    score = 0.55 * strength + 0.45 * trend
    return AnalyzerResult("relative_market", score, level2.confidence, {"strength": strength, "trend": trend})
