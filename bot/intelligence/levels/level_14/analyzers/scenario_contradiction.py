from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level13_result, level10_result) -> AnalyzerResult:
    continuation = level13_result.continuation
    reversal = level13_result.reversal
    adverse = level13_result.adverse_scenario
    readiness = level10_result.decision_readiness
    score = min(1.0, 0.45 * min(continuation, reversal) + 0.35 * adverse + 0.20 * (1.0 - readiness))
    return AnalyzerResult("scenario_contradiction", score, min(level13_result.confidence, level10_result.confidence))
