import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    momentum = snapshot.momentum
    if momentum is None:
        return AnalyzerResult("momentum", 0.0, 0.0, {"momentum": None}, ("momentum_missing",))
    if not isinstance(momentum, (int, float)) or not math.isfinite(momentum):
        return AnalyzerResult("momentum", 0.0, 0.0, {"momentum": None}, ("invalid_momentum",))
    score = min(max(0.5 + momentum * 5.0, 0.0), 1.0)
    return AnalyzerResult("momentum", score, 1.0, {"momentum": momentum})
