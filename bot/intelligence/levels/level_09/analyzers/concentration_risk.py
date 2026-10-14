from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level6_result) -> AnalyzerResult:
    positions = getattr(snapshot, "portfolio_positions", ())
    if not positions:
        if getattr(snapshot, "portfolio_context_available", False):
            return AnalyzerResult(
                "concentration_risk", 0.0, 1.0,
                {"position_count": 0, "herfindahl_index": 0.0, "largest_position_weight": 0.0},
                ["portfolio_confirmed_empty"],
            )
        return AnalyzerResult("concentration_risk", 0.0, 0.0, {"position_count": 0}, ["portfolio_positions_not_available"])
    valued_positions = [
        item for item in positions
        if item.get("market_value_available", True)
        and float(item.get("market_value", 0.0)) > 0
    ]
    values = [float(item.get("market_value", 0.0)) for item in valued_positions]
    total = sum(values)
    if total <= 0:
        return AnalyzerResult("concentration_risk", 0.0, 0.0, {"position_count": len(positions), "valued_position_count": 0}, ["portfolio_market_values_not_available"])
    shares = [value / total for value in values]
    hhi = sum(value * value for value in shares)
    coverage = len(valued_positions) / len(positions)
    confidence = min(1.0, len(shares) / 10.0) * coverage
    warnings = () if coverage >= 1.0 else ("some_position_market_values_unavailable",)
    return AnalyzerResult(
        "concentration_risk", max(0.0, min(1.0, hhi)), confidence,
        {"position_count": len(positions), "valued_position_count": len(valued_positions),
         "valuation_coverage": coverage, "herfindahl_index": hhi,
         "largest_position_weight": max(shares)},
        warnings,
    )
