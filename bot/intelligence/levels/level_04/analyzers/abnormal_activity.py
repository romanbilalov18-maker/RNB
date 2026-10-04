from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    volume = snapshot.volume / snapshot.average_volume if snapshot.average_volume > 0 else 1.0
    volatility = max(0.0, snapshot.volatility)
    score = min(1.0, max(0.0, (max(0.0, volume - 1.0) / 3.0) + min(1.0, volatility * 10.0) * 0.35))
    confidence = 0.75 if snapshot.average_volume > 0 else 0.3
    return AnalyzerResult(
        analyzer="abnormal_activity", score=score, confidence=confidence,
        metrics={"volume_ratio": volume, "volatility": volatility},
    )
