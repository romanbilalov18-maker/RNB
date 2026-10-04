from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    if snapshot.volatility is None:
        return AnalyzerResult("volatility", 0.5, 0.0, {"volatility": None}, ("volatility_missing",))
    score = min(max(1.0 - snapshot.volatility, 0.0), 1.0)
    return AnalyzerResult("volatility", score, 1.0, {"volatility": snapshot.volatility})
