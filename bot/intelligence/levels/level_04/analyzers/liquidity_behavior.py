from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    liquidity = min(1.0, max(0.0, snapshot.liquidity))
    volume = snapshot.volume / snapshot.average_volume if snapshot.average_volume > 0 else 1.0
    score = min(1.0, max(0.0, liquidity * 0.7 + min(1.0, volume / 2.0) * 0.3))
    return AnalyzerResult(
        analyzer="liquidity_behavior", score=score, confidence=0.8,
        metrics={"liquidity": liquidity, "volume_ratio": volume},
    )
