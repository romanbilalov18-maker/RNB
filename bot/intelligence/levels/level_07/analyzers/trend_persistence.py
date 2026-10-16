from bot.intelligence.core.models.analysis_result import AnalyzerResult
from ._validation import finite, metric, unavailable, upstream_context


def analyze(snapshot, level3_result) -> AnalyzerResult:
    warnings = upstream_context(snapshot, level3_result, "level3")
    momentum = finite(getattr(snapshot, "momentum", None))
    consistency = metric(level3_result, "consistency")
    confidence = metric(level3_result, "confidence")
    if warnings or None in (momentum, consistency, confidence):
        return unavailable("trend_persistence", warnings + ["trend_persistence_inputs_invalid"])
    directional = min(1.0, abs(momentum) * 10.0)
    score = min(1.0, directional * 0.65 + consistency * 0.35)
    return AnalyzerResult("trend_persistence", score, confidence, {"directional_strength": directional, "market_consistency": consistency})
