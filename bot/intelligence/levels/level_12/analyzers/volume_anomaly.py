from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot) -> AnalyzerResult:
    if snapshot.volume is None or snapshot.average_volume is None or snapshot.average_volume <= 0:
        return AnalyzerResult("volume_anomaly", 0.0, 0.0, {}, ("historical_volume_not_available",))
    ratio = snapshot.volume / snapshot.average_volume
    score = min(1.0, max(0.0, (ratio - 1.0) / 3.0))
    return AnalyzerResult("volume_anomaly", score, 0.95, {"volume_ratio": ratio})
