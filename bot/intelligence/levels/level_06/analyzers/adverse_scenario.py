from bot.intelligence.core.models.analysis_result import AnalyzerResult
from ._validation import number, confidence, level5_context, result_or_unavailable


def analyze(snapshot, level5_result) -> AnalyzerResult:
    warnings = level5_context(snapshot, level5_result)
    raw_confirmation = getattr(level5_result, "signal_confirmation", None) if level5_result is not None else None
    raw_volatility = getattr(snapshot, "volatility", None)
    confirmation = number(raw_confirmation, minimum=0.0, maximum=1.0)
    volatility = number(raw_volatility, minimum=0.0)
    components = []
    if confirmation is not None:
        components.append((min(1.0, max(0.0, 0.5 - confirmation)), 0.55))
    elif raw_confirmation is not None:
        warnings.append("signal_confirmation_input_invalid")
    if volatility is not None:
        components.append((min(1.0, volatility * 12.0), 0.45))
    elif raw_volatility is not None:
        warnings.append("volatility_input_invalid")
    if warnings or not components:
        return result_or_unavailable("adverse_scenario", warnings + ([] if components else ["adverse_scenario_inputs_not_available"]), {"observed_components": len(components)})
    level5_confidence = confidence(level5_result)
    if level5_confidence is None:
        return result_or_unavailable("adverse_scenario", ["level5_confidence_invalid"])
    weight_total = sum(weight for _, weight in components)
    score = sum(value * weight for value, weight in components) / weight_total
    return AnalyzerResult("adverse_scenario", score, level5_confidence * len(components) / 2.0, {
        "pressure_risk": min(1.0, max(0.0, 0.5 - confirmation)) if confirmation is not None else None,
        "volatility": min(1.0, volatility * 12.0) if volatility is not None else None,
        "observed_components": len(components),
    }, ("adverse_scenario_partial_inputs",) if len(components) == 1 else ())
