from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level5_result) -> AnalyzerResult:
    volatility = getattr(snapshot, "volatility", None)
    momentum = getattr(snapshot, "momentum", None)
    components = []
    if volatility is not None:
        components.append((max(0.0, float(volatility)) * 12.0, 0.65))
    if momentum is not None:
        components.append((max(0.0, -float(momentum)) * 5.0, 0.35))
    if not components:
        return AnalyzerResult(
            "downside_risk", 0.0, 0.0, {},
            ("volatility_and_momentum_not_available",),
        )
    total_weight = sum(weight for _, weight in components)
    score = min(1.0, sum(value * weight for value, weight in components) / total_weight)
    confidence = max(0.0, min(1.0, float(level5_result.confidence))) * len(components) / 2.0
    warnings = () if len(components) == 2 else ("downside_risk_partial_inputs",)
    return AnalyzerResult(
        "downside_risk", score, confidence,
        {"volatility": volatility,
         "negative_momentum": max(0.0, -float(momentum)) if momentum is not None else None,
         "observed_components": len(components)},
        warnings,
    )
