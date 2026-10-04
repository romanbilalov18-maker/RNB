from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level10_result, level13_result) -> AnalyzerResult:
    disagreement = 1.0 - level10_result.cross_level_agreement
    scenario_conflict = min(level13_result.continuation, level13_result.reversal)
    score = min(1.0, 0.65 * disagreement + 0.35 * scenario_conflict)
    return AnalyzerResult("signal_contradiction", score, min(level10_result.confidence, level13_result.confidence))
