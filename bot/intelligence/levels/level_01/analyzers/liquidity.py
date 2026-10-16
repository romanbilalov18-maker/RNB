import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    liquidity = snapshot.liquidity
    if liquidity is None:
        return AnalyzerResult("liquidity", 0.0, 0.0, {"liquidity": None}, ("liquidity_missing",))
    if (
        isinstance(liquidity, bool)
        or not isinstance(liquidity, (int, float))
        or not math.isfinite(liquidity)
        or not 0.0 <= liquidity <= 1.0
    ):
        return AnalyzerResult("liquidity", 0.0, 0.0, {"liquidity": None}, ("invalid_liquidity",))
    return AnalyzerResult("liquidity", float(liquidity), 1.0, {"liquidity": liquidity})
