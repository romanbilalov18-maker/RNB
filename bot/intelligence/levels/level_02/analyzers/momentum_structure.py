import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result


def analyze(snapshot: MarketSnapshot, level1: Level1Result) -> AnalyzerResult:
    base_result = next((r for r in level1.analyzer_results if r.analyzer == "momentum"), None)
    change = snapshot.price_change()
    momentum = snapshot.momentum
    if base_result is None or base_result.confidence <= 0 or change is None or momentum is None:
        return AnalyzerResult("momentum_structure", 0.0, 0.0,
                              {"change": change, "momentum": momentum},
                              ("insufficient_momentum_history",))
    if isinstance(momentum, bool) or not isinstance(momentum, (int, float)) or not math.isfinite(momentum):
        return AnalyzerResult("momentum_structure", 0.0, 0.0,
                              {"change": change, "momentum": None}, ("invalid_momentum",))
    # Both are expected to be fractional returns; expose raw inputs to diagnose producer unit drift.
    difference = abs(change - momentum)
    alignment = 1.0 - min(difference * 10.0, 1.0)
    score = 0.7 * base_result.score + 0.3 * alignment
    return AnalyzerResult("momentum_structure", score, min(base_result.confidence, level1.confidence),
                          {"alignment": alignment, "price_change": change, "momentum": momentum,
                           "absolute_difference": difference})
