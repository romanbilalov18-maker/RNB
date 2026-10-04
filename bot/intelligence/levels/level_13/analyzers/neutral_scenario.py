from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level10_result, level12_result) -> AnalyzerResult:
    stability = level10_result.confidence_quality
    anomaly = level12_result.score
    score = max(0.0, min(1.0, 0.65 * stability + 0.35 * (1.0 - anomaly)))
    return AnalyzerResult("neutral_scenario", score, min(level10_result.confidence, level12_result.confidence))
