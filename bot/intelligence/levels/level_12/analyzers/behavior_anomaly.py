from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level4_result) -> AnalyzerResult:
    score = max(
        level4_result.abnormal_activity,
        abs(level4_result.buying_pressure - level4_result.selling_pressure),
    )
    return AnalyzerResult("behavior_anomaly", min(1.0, score), level4_result.confidence)
