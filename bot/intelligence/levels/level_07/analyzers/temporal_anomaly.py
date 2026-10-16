from bot.intelligence.core.models.analysis_result import AnalyzerResult
from ._validation import finite, metric, unavailable, upstream_context


def analyze(snapshot, level4_result) -> AnalyzerResult:
    warnings = upstream_context(snapshot, level4_result, "level4")
    volume = finite(getattr(snapshot, "volume", None), 0.0)
    average = finite(getattr(snapshot, "average_volume", None), 0.0)
    abnormal = metric(level4_result, "abnormal_activity")
    confidence = metric(level4_result, "confidence")
    if warnings or None in (volume, average, abnormal, confidence):
        return unavailable("temporal_anomaly", warnings + ["temporal_anomaly_inputs_invalid"])
    if average == 0.0:
        return unavailable("temporal_anomaly", ["historical_volume_not_available"])
    ratio = volume / average
    volume_anomaly = min(1.0, max(0.0, (ratio - 1.0) / 3.0))
    score = min(1.0, volume_anomaly * 0.65 + abnormal * 0.35)
    return AnalyzerResult("temporal_anomaly", score, confidence, {"volume_ratio": ratio})
