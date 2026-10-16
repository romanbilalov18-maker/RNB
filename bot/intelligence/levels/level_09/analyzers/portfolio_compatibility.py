import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult


def _market_value(item: dict) -> float | None:
    if not item.get("market_value_available", True):
        return None
    try:
        value = float(item.get("market_value"))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value >= 0.0 else None


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
        return AnalyzerResult(
            "portfolio_compatibility", 0.0, 1.0,
            {"already_held": True, "position_count": len(positions)},
            ["candidate_already_in_portfolio"],
        )
    if not snapshot.sector:
        return AnalyzerResult("portfolio_compatibility", 0.0, 0.0, {"position_count": len(positions)}, ["candidate_sector_not_available"])

    sector_values = {}
    total_value = 0.0
    known_value = 0.0
    valued_count = 0
    invalid_count = 0
    for item in positions:
        value = _market_value(item)
        if value is None:
            invalid_count += 1
            continue
        total_value += value
        valued_count += 1
        sector = item.get("sector")
        if isinstance(sector, str) and sector.strip():
            sector = sector.strip()
            sector_values[sector] = sector_values.get(sector, 0.0) + value
            known_value += value

    if total_value <= 0.0 or known_value <= 0.0:
        return AnalyzerResult(
            "portfolio_compatibility", 0.0, 0.0,
            {"position_count": len(positions), "valued_position_count": valued_count},
            ["portfolio_sector_exposure_not_available"],
        )

    same_sector_weight = sector_values.get(snapshot.sector, 0.0) / known_value
    score = max(0.0, min(1.0, 1.0 - same_sector_weight))
    value_coverage = known_value / total_value
    position_coverage = valued_count / len(positions)
    confidence = min(1.0, valued_count / 10.0) * value_coverage * position_coverage
    warnings = []
    if value_coverage < 1.0:
        warnings.append("some_position_sectors_unavailable")
    if invalid_count:
        warnings.append("some_position_market_values_invalid")
    return AnalyzerResult(
        "portfolio_compatibility", score, max(0.0, min(1.0, confidence)),
        {"position_count": len(positions), "valued_position_count": valued_count,
         "candidate_sector": snapshot.sector, "existing_sector_weight": same_sector_weight,
         "known_sector_exposure": value_coverage, "invalid_value_count": invalid_count},
        warnings,
    )
