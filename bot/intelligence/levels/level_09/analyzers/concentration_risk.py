import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level6_result) -> AnalyzerResult:
    positions = getattr(snapshot, "portfolio_positions", ())
    if not positions:
        if getattr(snapshot, "portfolio_context_available", False):
            return AnalyzerResult(
                "concentration_risk", 0.0, 0.0,
                {"position_count": 0, "herfindahl_index": 0.0, "largest_position_weight": 0.0},
                ["portfolio_confirmed_empty", "portfolio_concentration_not_applicable"],
            )
        return AnalyzerResult("concentration_risk", 0.0, 0.0, {"position_count": 0}, ["portfolio_positions_not_available"])

    valued_positions = []
    invalid_values = 0
    for item in positions:
        if not item.get("market_value_available", True):
            continue
        try:
            value = float(item.get("market_value"))
        except (TypeError, ValueError):
            invalid_values += 1
            continue
        if not math.isfinite(value) or value <= 0:
            invalid_values += 1
            continue
        valued_positions.append(value)

    total = sum(valued_positions)
    if total <= 0:
        return AnalyzerResult(
            "concentration_risk", 0.0, 0.0,
            {"position_count": len(positions), "valued_position_count": 0},
            ["portfolio_market_values_not_available"],
        )
    shares = [value / total for value in valued_positions]
    hhi = sum(value * value for value in shares)
    coverage = len(valued_positions) / len(positions)
    confidence = min(1.0, len(shares) / 10.0) * coverage
    warnings = []
    if coverage < 1.0:
        warnings.append("some_position_market_values_unavailable")
    if invalid_values:
        warnings.append("invalid_position_market_values")
    return AnalyzerResult(
        "concentration_risk", max(0.0, min(1.0, hhi)), confidence,
        {"position_count": len(positions), "valued_position_count": len(valued_positions),
         "valuation_coverage": coverage, "herfindahl_index": hhi,
         "largest_position_weight": max(shares), "invalid_value_count": invalid_values},
        warnings,
    )
