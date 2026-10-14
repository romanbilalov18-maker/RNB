from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result


def analyze(snapshot: MarketSnapshot, level1: Level1Result) -> AnalyzerResult:
    momentum = snapshot.momentum
    price_result = next((r for r in level1.analyzer_results if r.analyzer == "price"), None)
    if price_result is None or price_result.confidence <= 0:
        return AnalyzerResult("trend", 0.0, 0.0, {"momentum": momentum}, ("price_signal_unavailable",))
    if momentum is None:
        return AnalyzerResult("trend", 0.0, 0.0, {"momentum": None}, ("momentum_missing",))
    direction = min(max(0.5 + momentum * 5.0, 0.0), 1.0)
    score = 0.6 * direction + 0.4 * price_result.score
    return AnalyzerResult("trend", score, min(price_result.confidence, level1.confidence), {"direction": direction, "price_score": price_result.score})
