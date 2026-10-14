from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    change = snapshot.price_change()
    if change is None:
        return AnalyzerResult("selling_pressure", 0.0, 0.0, {}, ("price_change_not_available",))
    volume_ratio = snapshot.volume_ratio
    if volume_ratio is None and snapshot.volume is not None and snapshot.average_volume is not None and snapshot.average_volume > 0:
        volume_ratio = snapshot.volume / snapshot.average_volume
    volume_bonus = max(0.0, volume_ratio - 1.0) * 0.12 if volume_ratio is not None else 0.0
    score = min(1.0, max(0.0, 0.5 - change * 8.0 + volume_bonus))
    confidence = 0.8 if volume_ratio is not None else 0.5
    return AnalyzerResult("selling_pressure", score, confidence, {"price_change": change, "volume_ratio": volume_ratio})
