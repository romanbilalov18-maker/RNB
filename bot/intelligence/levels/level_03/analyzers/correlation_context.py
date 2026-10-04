from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


def analyze(snapshot: MarketSnapshot, level2: Level2Result) -> AnalyzerResult:
    consistency = level2.consistency
    return AnalyzerResult("correlation_context", consistency, level2.confidence, {"proxy_consistency": consistency}, ("cross_asset_correlation_not_available",))
