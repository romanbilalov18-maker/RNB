from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level2_result, level3_result, level4_result) -> AnalyzerResult:
    values = [level2_result.score, level3_result.score, level4_result.score]
    spread = max(values) - min(values)
    score = max(0.0, min(1.0, 1.0 - spread))
    confidence = max(0.0, min(1.0, (level2_result.confidence + level3_result.confidence + level4_result.confidence) / 3.0))
    return AnalyzerResult("signal_consistency", score, confidence, {"spread": spread})
