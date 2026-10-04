from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result


def analyze(snapshot: MarketSnapshot, level1: Level1Result) -> AnalyzerResult:
    price = next((r.score for r in level1.analyzer_results if r.analyzer == "price"), 0.5)
    change = snapshot.price_change()
    if change is None:
        return AnalyzerResult("price_structure", price, 0.0, {"change": None}, ("previous_price_missing",))
    direction = 1.0 if change > 0 else 0.0 if change < 0 else 0.5
    score = 0.7 * price + 0.3 * direction
    return AnalyzerResult("price_structure", score, level1.confidence, {"direction": direction, "change": change})
