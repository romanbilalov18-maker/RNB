from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result


def analyze(snapshot: MarketSnapshot, level1: Level1Result) -> AnalyzerResult:
    price_result = next((r for r in level1.analyzer_results if r.analyzer == "price"), None)
    change = snapshot.price_change()
    if price_result is None or price_result.confidence <= 0 or change is None:
        return AnalyzerResult("price_structure", 0.0, 0.0, {"change": change}, ("price_structure_inputs_unavailable",))
    direction = 1.0 if change > 0 else 0.0 if change < 0 else 0.5
    score = 0.7 * price_result.score + 0.3 * direction
    return AnalyzerResult("price_structure", score, min(price_result.confidence, level1.confidence), {"direction": direction, "change": change})
