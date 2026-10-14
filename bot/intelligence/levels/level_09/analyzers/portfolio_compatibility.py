from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level5_result, level8_result) -> AnalyzerResult:
    positions = getattr(snapshot, "portfolio_positions", ())
    if not positions:
        return AnalyzerResult("portfolio_compatibility", 0.0, 0.0, {"position_count": 0}, ["existing_positions_not_available"])
    symbols = {item.get("symbol") for item in positions}
    if snapshot.symbol in symbols:
        return AnalyzerResult("portfolio_compatibility", 0.0, 0.0, {"already_held": True}, ["candidate_already_in_portfolio"])
    return AnalyzerResult("portfolio_compatibility", level5_result.score, min(level5_result.confidence, level8_result.confidence, min(1.0, len(positions) / 10.0)), {"position_count": len(positions), "already_held": False})
