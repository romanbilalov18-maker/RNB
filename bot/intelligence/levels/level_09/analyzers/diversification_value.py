import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level8_result) -> AnalyzerResult:
    positions = getattr(snapshot, "portfolio_positions", ())
    if not positions:
        if getattr(snapshot, "portfolio_context_available", False):
            return AnalyzerResult(
                "diversification_value", 0.0, 0.0,
                {"position_count": 0, "distinct_sectors": 0, "sector_coverage": 0.0},
                ["portfolio_confirmed_empty", "portfolio_diversification_not_applicable"],
            )
        return AnalyzerResult("diversification_value", 0.0, 0.0, {"position_count": 0}, ["portfolio_positions_not_available"])

    total_value = 0.0
    known_sector_value = 0.0
    sector_values = {}
    valued_positions = 0
    for item in positions:
        raw_value = item.get("market_value")
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value) or value <= 0 or not item.get("market_value_available", True):
            continue
        total_value += value
        valued_positions += 1
        sector = item.get("sector")
        if isinstance(sector, str) and sector.strip():
            known_sector_value += value
            sector_values[sector.strip()] = sector_values.get(sector.strip(), 0.0) + value

    if total_value <= 0 or known_sector_value <= 0:
        return AnalyzerResult(
            "diversification_value", 0.0, 0.0,
            {"position_count": len(positions), "valued_position_count": valued_positions},
            ["portfolio_sector_exposure_not_available"],
        )

    weights = [value / known_sector_value for value in sector_values.values()]
    hhi = sum(weight * weight for weight in weights)
    sector_count = len(weights)
    # Normalize sector HHI so a perfectly equal allocation across known sectors
    # scores 1, while a portfolio concentrated in one sector scores 0.
    score = (1.0 - hhi) / (1.0 - 1.0 / sector_count) if sector_count > 1 else 0.0
    score = max(0.0, min(1.0, score))
    value_coverage = known_sector_value / total_value
    position_coverage = valued_positions / len(positions)
    confidence = min(1.0, valued_positions / 10.0) * value_coverage * position_coverage
    warnings = () if value_coverage >= 1.0 else ("some_position_sectors_unavailable",)
    return AnalyzerResult(
        "diversification_value", score, max(0.0, min(1.0, confidence)),
        {
            "position_count": len(positions),
            "valued_position_count": valued_positions,
            "distinct_sectors": sector_count,
            "sector_hhi": hhi,
            "sector_coverage": value_coverage,
            "sector_weights": {sector: value / known_sector_value for sector, value in sector_values.items()},
        },
        warnings,
    )
