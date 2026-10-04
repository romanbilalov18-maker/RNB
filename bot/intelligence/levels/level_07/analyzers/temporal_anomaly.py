from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level4_result) -> AnalyzerResult:
    volume_ratio = snapshot.volume / snapshot.average_volume if snapshot.average_volume > 0 else 1.0
    volume_anomaly = min(1.0, max(0.0, (volume_ratio - 1.0) / 3.0))
    score = min(1.0, volume_anomaly * 0.65 + level4_result.abnormal_activity * 0.35)
    warnings = [] if snapshot.average_volume > 0 else ["historical_volume_not_available"]
    return AnalyzerResult("temporal_anomaly", score, level4_result.confidence, {"volume_ratio": volume_ratio}, warnings)
