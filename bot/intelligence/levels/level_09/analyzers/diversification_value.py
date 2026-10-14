from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level8_result) -> AnalyzerResult:
    positions = getattr(snapshot, "portfolio_positions", ())
    if len(positions) < 2:
        return AnalyzerResult("diversification_value", 0.0, 0.0, {"position_count": len(positions)}, ["portfolio_composition_insufficient"])
    sectors = [item.get("sector") for item in positions if item.get("sector")]
    distinct_sectors = len(set(sectors))
    coverage = len(sectors) / len(positions)
    score = min(1.0, (distinct_sectors / len(positions)) * coverage)
    return AnalyzerResult("diversification_value", score, min(1.0, len(positions) / 10.0), {"position_count": len(positions), "distinct_sectors": distinct_sectors, "sector_coverage": coverage})
