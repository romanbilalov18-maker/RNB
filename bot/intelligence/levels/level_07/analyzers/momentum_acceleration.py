from bot.intelligence.core.models.analysis_result import AnalyzerResult
from ._validation import finite, unavailable


def analyze(snapshot, level6_result) -> AnalyzerResult:
    raw = getattr(snapshot, "historical_returns", None)
    if raw is None:
        return unavailable("momentum_acceleration", ["historical_returns_not_available"])
    try:
        values = [finite(value) for value in raw]
    except TypeError:
        return unavailable("momentum_acceleration", ["historical_returns_invalid"])
    valid = [value for value in values if value is not None]
    invalid_count = len(values) - len(valid)
    if len(valid) < 8:
        return unavailable("momentum_acceleration", ["historical_momentum_series_insufficient"] + (["historical_returns_invalid_observations"] if invalid_count else []), {"observations": len(valid), "invalid_observations": invalid_count})
    recent = sum(valid[-3:]) / 3.0
    prior = sum(valid[-6:-3]) / 3.0
    acceleration = recent - prior
    score = max(0.0, min(1.0, 0.5 + acceleration * 8.0))
    confidence = min(1.0, len(valid) / 30.0) * len(valid) / len(values)
    warnings = ("historical_returns_invalid_observations",) if invalid_count else ()
    return AnalyzerResult("momentum_acceleration", score, confidence, {"recent_mean_return": recent, "prior_mean_return": prior, "acceleration": acceleration, "observations": len(valid), "invalid_observations": invalid_count}, warnings)
