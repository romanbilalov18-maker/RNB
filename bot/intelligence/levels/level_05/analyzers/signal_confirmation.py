from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level2_result, level4_result) -> AnalyzerResult:
    agreement = 1.0 - abs(level2_result.score - level4_result.score)
    score = max(0.0, min(1.0, agreement))
    confidence = max(0.0, min(1.0, (level2_result.confidence + level4_result.confidence) / 2.0))
    return AnalyzerResult("signal_confirmation", score, confidence, {
        "level2_score": level2_result.score, "level4_score": level4_result.score
    })
