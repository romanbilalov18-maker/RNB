from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level3_result) -> AnalyzerResult:
    if snapshot.sector is None or snapshot.sector_return is None or snapshot.peer_count < 2:
        return AnalyzerResult("sector_relative_strength", 0.0, 0.0, {"sector": snapshot.sector, "peer_count": snapshot.peer_count}, ["sector_data_not_available"])
    relative = snapshot.sector_return - snapshot.market_return if snapshot.market_return is not None else snapshot.sector_return
    score = max(0.0, min(1.0, 0.5 + relative * 8.0))
    return AnalyzerResult("sector_relative_strength", score, min(1.0, snapshot.peer_count / 10.0), {"sector": snapshot.sector, "sector_return": snapshot.sector_return, "market_return": snapshot.market_return, "relative_return": relative, "peer_count": snapshot.peer_count})
