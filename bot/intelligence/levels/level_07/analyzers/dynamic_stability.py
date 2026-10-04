from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level5_result, level6_result) -> AnalyzerResult:
    score = min(1.0, max(0.0, (level5_result.signal_stability + level6_result.consistency) / 2.0))
    confidence = min(level5_result.confidence, level6_result.confidence)
    return AnalyzerResult("dynamic_stability", score, confidence, {"signal_stability": level5_result.signal_stability, "risk_consistency": level6_result.consistency})
