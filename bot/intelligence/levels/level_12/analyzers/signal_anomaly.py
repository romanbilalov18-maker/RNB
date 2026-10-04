from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level7_result, level10_result) -> AnalyzerResult:
    transition = getattr(level7_result, "regime_transition", 0.5)
    readiness = getattr(level10_result, "decision_readiness", 0.5)
    score = min(1.0, abs(transition - readiness) * 2.0)
    return AnalyzerResult("signal_anomaly", score, min(level7_result.confidence, level10_result.confidence))
