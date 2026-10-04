from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result


def analyze(snapshot: MarketSnapshot, level1: Level1Result) -> AnalyzerResult:
    base = next((r.score for r in level1.analyzer_results if r.analyzer == "momentum"), 0.5)
    change = snapshot.price_change()
    if change is None or snapshot.momentum is None:
        return AnalyzerResult("momentum_structure", base, 0.0, {"change": change}, ("insufficient_history",))
    alignment = 1.0 - min(abs(change - snapshot.momentum) * 10.0, 1.0)
    score = 0.7 * base + 0.3 * alignment
    return AnalyzerResult("momentum_structure", score, level1.confidence, {"alignment": alignment})
