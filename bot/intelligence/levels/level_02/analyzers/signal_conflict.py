from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result


def analyze(snapshot: MarketSnapshot, level1: Level1Result) -> AnalyzerResult:
    scores = [r.score for r in level1.analyzer_results if r.analyzer != "data_quality"]
    if not scores:
        return AnalyzerResult("signal_conflict", 0.0, 0.0, {}, ("no_analyzer_results",))
    spread = max(scores) - min(scores)
    consistency = max(0.0, 1.0 - spread)
    return AnalyzerResult("signal_conflict", consistency, level1.confidence, {"score_spread": spread, "consistency": consistency})
