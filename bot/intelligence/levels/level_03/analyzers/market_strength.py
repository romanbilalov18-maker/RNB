from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


def analyze(snapshot: MarketSnapshot, level2: Level2Result) -> AnalyzerResult:
    relative = next((r.score for r in level2.analyzer_results if r.analyzer == "relative_strength"), 0.5)
    volume = next((r.score for r in level2.analyzer_results if r.analyzer == "volume_flow"), 0.5)
    score = 0.60 * relative + 0.40 * volume
    return AnalyzerResult("market_strength", score, level2.confidence, {"relative_strength": relative, "volume_flow": volume})
