from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level4_result) -> AnalyzerResult:
    if snapshot.peer_return is None or snapshot.peer_count < 2:
        return AnalyzerResult("peer_context", 0.0, 0.0, {"peer_count": snapshot.peer_count}, ["peer_universe_not_available"])
    change = snapshot.price_change()
    relative = change - snapshot.peer_return if change is not None else None
    if relative is None:
        return AnalyzerResult("peer_context", 0.0, 0.0, {"peer_return": snapshot.peer_return}, ["asset_return_not_available"])
    score = max(0.0, min(1.0, 0.5 + relative * 8.0))
    return AnalyzerResult("peer_context", score, min(1.0, snapshot.peer_count / 10.0), {"asset_return": change, "peer_return": snapshot.peer_return, "relative_return": relative, "peer_count": snapshot.peer_count})
