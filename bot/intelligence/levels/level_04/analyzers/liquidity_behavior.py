from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    if snapshot.liquidity is None:
        return AnalyzerResult("liquidity_behavior", 0.0, 0.0, {}, ("liquidity_data_not_available",))
    liquidity = min(1.0, max(0.0, snapshot.liquidity))
    volume_ratio = snapshot.volume_ratio
    if volume_ratio is None and snapshot.volume is not None and snapshot.average_volume is not None and snapshot.average_volume > 0:
        volume_ratio = snapshot.volume / snapshot.average_volume
    if volume_ratio is None:
        return AnalyzerResult("liquidity_behavior", liquidity, 0.5, {"liquidity": liquidity, "volume_ratio": None})
    score = min(1.0, max(0.0, liquidity * 0.7 + min(1.0, volume_ratio / 2.0) * 0.3))
    return AnalyzerResult("liquidity_behavior", score, 0.8, {"liquidity": liquidity, "volume_ratio": volume_ratio})
