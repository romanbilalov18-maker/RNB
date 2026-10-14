from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level5_result, level8_result) -> AnalyzerResult:
    positions = getattr(snapshot, "portfolio_positions", ())
    if not positions:
        if getattr(snapshot, "portfolio_context_available", False) and snapshot.sector:
            return AnalyzerResult(
                "portfolio_compatibility", 1.0, 1.0,
                {"position_count": 0, "candidate_sector": snapshot.sector, "existing_sector_weight": 0.0},
                ["portfolio_confirmed_empty"],
            )
        warning = "candidate_sector_not_available" if getattr(snapshot, "portfolio_context_available", False) else "existing_positions_not_available"
        return AnalyzerResult("portfolio_compatibility", 0.0, 0.0, {"position_count": 0}, [warning])
    if any(item.get("symbol") == snapshot.symbol for item in positions):
        return AnalyzerResult("portfolio_compatibility", 0.0, 1.0, {"already_held": True, "position_count": len(positions)}, ["candidate_already_in_portfolio"])
    if not snapshot.sector:
        return AnalyzerResult("portfolio_compatibility", 0.0, 0.0, {"position_count": len(positions)}, ["candidate_sector_not_available"])
    sector_values = {}
    known_value = 0.0
    total_value = sum(max(0.0, float(item.get("market_value", 0.0))) for item in positions)
    for item in positions:
        value = max(0.0, float(item.get("market_value", 0.0)))
        sector = item.get("sector")
        if sector:
            sector_values[sector] = sector_values.get(sector, 0.0) + value
            known_value += value
    if total_value <= 0 or known_value <= 0:
        return AnalyzerResult("portfolio_compatibility", 0.0, 0.0, {"position_count": len(positions)}, ["portfolio_sector_exposure_not_available"])
    same_sector_weight = sector_values.get(snapshot.sector, 0.0) / total_value
    score = max(0.0, min(1.0, 1.0 - same_sector_weight))
    confidence = min(1.0, len(positions) / 10.0) * (known_value / total_value)
    return AnalyzerResult("portfolio_compatibility", score, confidence, {"position_count": len(positions), "candidate_sector": snapshot.sector, "existing_sector_weight": same_sector_weight, "known_sector_exposure": known_value / total_value})
