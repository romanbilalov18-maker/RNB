from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level12_result, level10_result) -> AnalyzerResult:
    anomaly = level12_result.score
    confidence = level10_result.confidence
    score = min(1.0, 0.70 * anomaly + 0.30 * (1.0 - confidence))
    return AnalyzerResult("anomaly_contradiction", score, min(level12_result.confidence, level10_result.confidence))
