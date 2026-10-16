from bot.intelligence.core.models.analysis_result import AnalyzerResult
from ._validation import finite, metric, unavailable, upstream_context


def analyze(snapshot, level6_result) -> AnalyzerResult:
    warnings = upstream_context(snapshot, level6_result, "level6")
    momentum = finite(getattr(snapshot, "momentum", None))
    volatility = finite(getattr(snapshot, "volatility", None), 0.0)
    confidence = metric(level6_result, "confidence")
    if warnings or None in (momentum, volatility, confidence):
        return unavailable("movement_exhaustion", warnings + ["movement_exhaustion_inputs_invalid"])
    extension = min(1.0, abs(momentum) * 8.0)
    volatility_score = min(1.0, volatility * 12.0)
    score = min(1.0, extension * 0.65 + volatility_score * 0.35)
    return AnalyzerResult("movement_exhaustion", score, confidence, {"extension": extension, "volatility": volatility_score})
