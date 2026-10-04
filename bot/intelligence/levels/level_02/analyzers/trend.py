from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result


def analyze(snapshot: MarketSnapshot, level1: Level1Result) -> AnalyzerResult:
    momentum = snapshot.momentum
    price_score = next((r.score for r in level1.analyzer_results if r.analyzer == "price"), 0.5)
    if momentum is None:
        return AnalyzerResult("trend", price_score, 0.0, {"momentum": None}, ("momentum_missing",))
    direction = min(max(0.5 + momentum * 5.0, 0.0), 1.0)
    score = 0.6 * direction + 0.4 * price_score
    return AnalyzerResult("trend", score, level1.confidence, {"direction": direction, "price_score": price_score})
