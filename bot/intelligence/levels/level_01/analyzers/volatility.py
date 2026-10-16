import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    volatility = snapshot.volatility
    if volatility is None:
        return AnalyzerResult("volatility", 0.0, 0.0, {"volatility": None}, ("volatility_missing",))
    if (
        isinstance(volatility, bool)
        or not isinstance(volatility, (int, float))
        or not math.isfinite(volatility)
        or volatility < 0
    ):
        return AnalyzerResult("volatility", 0.0, 0.0, {"volatility": None}, ("invalid_volatility",))
    score = min(max(1.0 - volatility, 0.0), 1.0)
    return AnalyzerResult("volatility", score, 1.0, {"volatility": volatility})
