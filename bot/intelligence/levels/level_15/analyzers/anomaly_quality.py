from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(l12) -> AnalyzerResult:
    score = 1.0 - l12.score
    return AnalyzerResult("anomaly_quality", max(0.0, score), l12.confidence)
