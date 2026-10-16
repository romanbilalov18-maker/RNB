from bot.intelligence.core.models.analysis_result import AnalyzerResult
from ._validation import number, confidence, level5_context, result_or_unavailable


def analyze(snapshot, level5_result) -> AnalyzerResult:
    warnings = level5_context(snapshot, level5_result)
    volatility = number(getattr(snapshot, "volatility", None), minimum=0.0)
    momentum = number(getattr(snapshot, "momentum", None))
    components = []
    if volatility is not None:
        components.append((min(1.0, volatility * 12.0), 0.65))
    elif getattr(snapshot, "volatility", None) is not None:
        warnings.append("volatility_input_invalid")
    if momentum is not None:
        components.append((min(1.0, max(0.0, -momentum) * 5.0), 0.35))
    elif getattr(snapshot, "momentum", None) is not None:
        warnings.append("momentum_input_invalid")
    if not components or warnings:
        return result_or_unavailable("downside_risk", warnings + ([] if components else ["volatility_and_momentum_not_available"]), {"observed_components": len(components)})
    level5_confidence = confidence(level5_result)
    if level5_confidence is None:
        return result_or_unavailable("downside_risk", ["level5_confidence_invalid"])
    total_weight = sum(weight for _, weight in components)
    score = sum(value * weight for value, weight in components) / total_weight
    output_confidence = level5_confidence * len(components) / 2.0
    return AnalyzerResult("downside_risk", score, output_confidence, {
        "volatility": volatility, "negative_momentum": max(0.0, -momentum) if momentum is not None else None,
        "observed_components": len(components),
    }, ("downside_risk_partial_inputs",) if len(components) == 1 else ())
