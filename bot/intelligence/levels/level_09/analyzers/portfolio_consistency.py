from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level5_result, level6_result, level8_result) -> AnalyzerResult:
    values = [level5_result.score, level6_result.score, level8_result.score]
    spread = max(values) - min(values)
    score = min(1.0, max(0.0, 1.0 - spread))
    confidence = min(level5_result.confidence, level6_result.confidence, level8_result.confidence)
    return AnalyzerResult("portfolio_consistency", score, confidence, {"spread": spread})
