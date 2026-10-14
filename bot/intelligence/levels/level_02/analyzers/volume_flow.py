from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result


def analyze(snapshot: MarketSnapshot, level1: Level1Result) -> AnalyzerResult:
    base_result = next((r for r in level1.analyzer_results if r.analyzer == "volume"), None)
    change = snapshot.price_change()
    ratio = None
    if snapshot.volume is not None and snapshot.average_volume not in (None, 0):
        ratio = snapshot.volume / snapshot.average_volume
    if base_result is None or base_result.confidence <= 0 or change is None or ratio is None:
        return AnalyzerResult("volume_flow", 0.0, 0.0, {"ratio": ratio}, ("insufficient_volume_history",))
    confirmation = min(max(0.5 + (ratio - 1.0) * 0.5, 0.0), 1.0) if change > 0 else min(max(0.5 - (ratio - 1.0) * 0.5, 0.0), 1.0)
    score = 0.5 * base_result.score + 0.5 * confirmation
    return AnalyzerResult("volume_flow", score, min(base_result.confidence, level1.confidence), {"ratio": ratio, "confirmation": confirmation})
