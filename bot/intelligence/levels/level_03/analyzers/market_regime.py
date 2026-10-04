from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


def analyze(snapshot: MarketSnapshot, level2: Level2Result) -> AnalyzerResult:
    trend = next((r.score for r in level2.analyzer_results if r.analyzer == "trend"), 0.5)
    volatility = next((r.score for r in level2.analyzer_results if r.analyzer == "price_structure"), 0.5)
    score = 0.65 * trend + 0.35 * volatility
    return AnalyzerResult("market_regime", score, level2.confidence, {"trend_score": trend, "structure_score": volatility})
