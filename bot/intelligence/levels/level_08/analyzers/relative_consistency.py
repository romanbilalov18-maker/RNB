from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level3_result, level7_result) -> AnalyzerResult:
    score = max(0.0, min(1.0, 1.0 - abs(level3_result.score - level7_result.score)))
    confidence = min(level3_result.confidence, level7_result.confidence)
    return AnalyzerResult("relative_consistency", score, confidence, {"level3_score": level3_result.score, "level7_score": level7_result.score})
