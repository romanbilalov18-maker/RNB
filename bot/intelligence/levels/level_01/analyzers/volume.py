from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    if snapshot.volume is None or snapshot.average_volume in (None, 0):
        return AnalyzerResult("volume", 0.5, 0.0, {"ratio": None}, ("volume_missing",))
    ratio = snapshot.volume / snapshot.average_volume
    score = min(max(ratio / 2.0, 0.0), 1.0)
    return AnalyzerResult("volume", score, 1.0, {"ratio": ratio})
