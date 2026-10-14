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
    values = [float(item.get("market_value", 0.0)) for item in positions if float(item.get("market_value", 0.0)) > 0]
    total = sum(values)
    if total <= 0:
        return AnalyzerResult("concentration_risk", 0.0, 0.0, {"position_count": len(positions)}, ["portfolio_market_values_not_available"])
    shares = [value / total for value in values]
    hhi = sum(value * value for value in shares)
    return AnalyzerResult("concentration_risk", max(0.0, min(1.0, hhi)), min(1.0, len(shares) / 10.0), {"position_count": len(shares), "herfindahl_index": hhi, "largest_position_weight": max(shares)})
