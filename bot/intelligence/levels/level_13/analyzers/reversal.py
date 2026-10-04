from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level7_result, level10_result) -> AnalyzerResult:
    exhaustion = level7_result.movement_exhaustion
    transition = level7_result.regime_transition
    disagreement = 1.0 - level10_result.cross_level_agreement
    score = min(1.0, 0.40 * exhaustion + 0.35 * transition + 0.25 * disagreement)
    return AnalyzerResult("reversal", score, min(level7_result.confidence, level10_result.confidence))
