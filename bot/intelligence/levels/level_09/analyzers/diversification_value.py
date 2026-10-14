from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level8_result) -> AnalyzerResult:
    positions = getattr(snapshot, "portfolio_positions", ())
    if not positions:
        if getattr(snapshot, "portfolio_context_available", False):
            return AnalyzerResult(
                "diversification_value", 0.0, 1.0,
                {"position_count": 0, "distinct_sectors": 0, "sector_coverage": 1.0},
                ["portfolio_confirmed_empty"],
            )
        return AnalyzerResult("diversification_value", 0.0, 0.0, {"position_count": 0}, ["portfolio_positions_not_available"])
    sectors = [item.get("sector") for item in positions if item.get("sector")]
    distinct_sectors = len(set(sectors))
    coverage = len(sectors) / len(positions)
    score = min(1.0, (distinct_sectors / len(positions)) * coverage)
    return AnalyzerResult("diversification_value", score, min(1.0, len(positions) / 10.0), {"position_count": len(positions), "distinct_sectors": distinct_sectors, "sector_coverage": coverage})
