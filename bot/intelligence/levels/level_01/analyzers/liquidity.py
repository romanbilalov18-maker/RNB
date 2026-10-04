from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    if snapshot.liquidity is None:
        return AnalyzerResult("liquidity", 0.5, 0.0, {"liquidity": None}, ("liquidity_missing",))
    score = min(max(snapshot.liquidity, 0.0), 1.0)
    return AnalyzerResult("liquidity", score, 1.0, {"liquidity": snapshot.liquidity})
