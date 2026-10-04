from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    change = snapshot.price_change()
    if change is None:
        return AnalyzerResult("price", 0.5, 0.0, {"change": None}, ("previous_price_missing",))
    score = min(max(0.5 + change * 5.0, 0.0), 1.0)
    return AnalyzerResult("price", score, 1.0, {"change": change})
