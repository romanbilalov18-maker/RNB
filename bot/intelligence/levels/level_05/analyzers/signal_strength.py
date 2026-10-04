from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level3_result, level4_result) -> AnalyzerResult:
    score = max(0.0, min(1.0, level3_result.score * 0.55 + level4_result.score * 0.45))
    confidence = max(0.0, min(1.0, (level3_result.confidence + level4_result.confidence) / 2.0))
    return AnalyzerResult("signal_strength", score, confidence, {
        "level3_score": level3_result.score, "level4_score": level4_result.score
    })
