from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result


def analyze(snapshot: MarketSnapshot, level1: Level1Result) -> AnalyzerResult:
    momentum = next((r.score for r in level1.analyzer_results if r.analyzer == "momentum"), 0.5)
    liquidity = next((r.score for r in level1.analyzer_results if r.analyzer == "liquidity"), 0.5)
    score = 0.65 * momentum + 0.35 * liquidity
    return AnalyzerResult("relative_strength", score, level1.confidence, {"momentum_score": momentum, "liquidity_score": liquidity})
