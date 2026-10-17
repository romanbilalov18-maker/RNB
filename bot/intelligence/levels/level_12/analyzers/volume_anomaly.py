from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot) -> AnalyzerResult:
    if snapshot.volume is None or snapshot.average_volume is None or snapshot.average_volume <= 0:
        return AnalyzerResult("volume_anomaly", 0.0, 0.0, {}, ("historical_volume_not_available",))
    ratio = snapshot.volume / snapshot.average_volume
    # Unusual volume can be either a surge or a collapse. Measure deviation
    # from the baseline in both directions instead of ignoring low volume.
    score = min(1.0, abs(ratio - 1.0) / 3.0)
    return AnalyzerResult("volume_anomaly", score, 0.95, {"volume_ratio": ratio})
