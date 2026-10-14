from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


def analyze(snapshot: MarketSnapshot, level2: Level2Result) -> AnalyzerResult:
    if snapshot.sector is None or snapshot.sector_return is None or snapshot.peer_count < 2:
        return AnalyzerResult(
            "sector_context", 0.0, 0.0,
            {"sector": snapshot.sector, "peer_count": snapshot.peer_count},
            ("sector_data_not_available",),
        )
    market_return = snapshot.market_return
    relative = snapshot.sector_return - market_return if market_return is not None else snapshot.sector_return
    score = max(0.0, min(1.0, 0.5 + relative * 8.0))
    confidence = min(1.0, snapshot.peer_count / 10.0)
    return AnalyzerResult(
        "sector_context", score, confidence,
        {"sector": snapshot.sector, "sector_return": snapshot.sector_return,
         "market_return": market_return, "relative_return": relative,
         "peer_count": snapshot.peer_count},
    )
