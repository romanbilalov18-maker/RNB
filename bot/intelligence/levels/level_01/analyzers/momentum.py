from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    if snapshot.momentum is None:
        return AnalyzerResult("momentum", 0.5, 0.0, {"momentum": None}, ("momentum_missing",))
    score = min(max(0.5 + snapshot.momentum * 5.0, 0.0), 1.0)
    return AnalyzerResult("momentum", score, 1.0, {"momentum": snapshot.momentum})
