import math
from bot.intelligence.core.models.analysis_result import AnalyzerResult


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def analyze(snapshot, level3_result) -> AnalyzerResult:
    sector = getattr(snapshot, "sector", None)
    sector_return = getattr(snapshot, "sector_return", None)
    peer_count = getattr(snapshot, "peer_count", None)
    market_return = getattr(snapshot, "market_return", None)
    if not isinstance(sector, str) or not sector or not _finite(sector_return) or not isinstance(peer_count, int) or isinstance(peer_count, bool) or peer_count < 2:
        return AnalyzerResult("sector_relative_strength", 0.0, 0.0, {"sector": sector, "peer_count": peer_count}, ("sector_data_not_available",))
    if not _finite(market_return):
        return AnalyzerResult("sector_relative_strength", 0.0, 0.0, {"sector": sector, "sector_return": sector_return, "peer_count": peer_count}, ("market_benchmark_not_available",))
    relative = sector_return - market_return
    score = max(0.0, min(1.0, 0.5 + relative * 8.0))
    return AnalyzerResult("sector_relative_strength", score, min(1.0, peer_count / 10.0), {"sector": sector, "sector_return": sector_return, "market_return": market_return, "relative_return": relative, "peer_count": peer_count})
