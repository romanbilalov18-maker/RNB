from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


def analyze(snapshot: MarketSnapshot, level2: Level2Result) -> AnalyzerResult:
    """Use available asset-level structure until sector data is supplied by a future adapter."""
    strength = next((r.score for r in level2.analyzer_results if r.analyzer == "relative_strength"), 0.5)
    return AnalyzerResult("sector_context", strength, level2.confidence * 0.75, {"proxy": "relative_strength"}, ("sector_data_not_available",))
