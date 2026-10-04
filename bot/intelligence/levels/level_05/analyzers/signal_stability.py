from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level3_result, level4_result) -> AnalyzerResult:
    score = max(0.0, min(1.0, (level3_result.consistency + level4_result.consistency) / 2.0))
    confidence = max(0.0, min(1.0, (level3_result.confidence + level4_result.confidence) / 2.0))
    return AnalyzerResult("signal_stability", score, confidence, {
        "level3_consistency": level3_result.consistency,
        "level4_consistency": level4_result.consistency,
    })
