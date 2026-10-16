import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


def analyze(snapshot: MarketSnapshot, level2: Level2Result) -> AnalyzerResult:
    sector_return = snapshot.sector_return
    market_return = snapshot.market_return
    peer_count = snapshot.peer_count

    # A sector return is meaningful here only relative to an observed market
    # benchmark. Never silently treat an absolute sector return as relative alpha.
    if (
        not snapshot.sector
        or isinstance(peer_count, bool)
        or not isinstance(peer_count, int)
        or peer_count < 2
        or not isinstance(sector_return, (int, float))
        or isinstance(sector_return, bool)
        or not math.isfinite(sector_return)
        or not isinstance(market_return, (int, float))
        or isinstance(market_return, bool)
        or not math.isfinite(market_return)
    ):
        return AnalyzerResult(
            "sector_context", 0.0, 0.0,
            {
                "sector": snapshot.sector,
                "peer_count": peer_count,
                "sector_return_available": isinstance(sector_return, (int, float)) and not isinstance(sector_return, bool) and math.isfinite(sector_return),
                "market_return_available": isinstance(market_return, (int, float)) and not isinstance(market_return, bool) and math.isfinite(market_return),
            },
            ("sector_data_not_available", "sector_relative_context_unavailable"),
        )

    relative = sector_return - market_return
    score = max(0.0, min(1.0, 0.5 + relative * 8.0))
    confidence = min(1.0, peer_count / 10.0)
    return AnalyzerResult(
        "sector_context", score, confidence,
        {
            "sector": snapshot.sector,
            "sector_return": sector_return,
            "market_return": market_return,
            "relative_return": relative,
            "peer_count": peer_count,
            "benchmark_source": "observed_market_return",
        },
    )
