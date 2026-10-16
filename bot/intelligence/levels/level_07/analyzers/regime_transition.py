from bot.intelligence.core.models.analysis_result import AnalyzerResult
from ._validation import finite, metric, unavailable, upstream_context


def analyze(snapshot, level3_result) -> AnalyzerResult:
    warnings = upstream_context(snapshot, level3_result, "level3")
    momentum = finite(getattr(snapshot, "momentum", None))
    market_score = metric(level3_result, "score")
    confidence = metric(level3_result, "confidence")
    if warnings or None in (momentum, market_score, confidence):
        return unavailable("regime_transition", warnings + ["regime_transition_inputs_invalid"])
    # A zero momentum has no direction and cannot establish a transition.
    if momentum == 0.0 or market_score == 0.5:
        return unavailable("regime_transition", ["regime_direction_ambiguous"])
    transition = (momentum > 0.0) != (market_score > 0.5)
    score = 0.8 if transition else 0.2
    return AnalyzerResult("regime_transition", score, confidence, {"transition_detected": transition})
