from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level5_result) -> AnalyzerResult:
    signal_confirmation = getattr(level5_result, "signal_confirmation", None)
    volatility = getattr(snapshot, "volatility", None)
    components = []
    pressure = None
    volatility_risk = None
    if signal_confirmation is not None:
        pressure = max(0.0, 0.5 - float(signal_confirmation))
        components.append((pressure, 0.55))
    if volatility is not None:
        volatility_risk = min(1.0, max(0.0, float(volatility) * 12.0))
        components.append((volatility_risk, 0.45))
    if not components:
        return AnalyzerResult(
            "adverse_scenario", 0.0, 0.0, {},
            ("adverse_scenario_inputs_not_available",),
        )
    weight_total = sum(weight for _, weight in components)
    score = min(1.0, max(0.0, sum(value * weight for value, weight in components) / weight_total))
    confidence = max(0.0, min(1.0, float(level5_result.confidence))) * len(components) / 2.0
    warnings = () if len(components) == 2 else ("adverse_scenario_partial_inputs",)
    return AnalyzerResult(
        "adverse_scenario", score, confidence,
        {"pressure_risk": pressure, "volatility": volatility_risk, "observed_components": len(components)},
        warnings,
    )
