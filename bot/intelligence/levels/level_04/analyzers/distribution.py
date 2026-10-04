from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    change = snapshot.price_change()
    volume = snapshot.volume / snapshot.average_volume if snapshot.average_volume > 0 else 1.0
    score = min(1.0, max(0.0, 0.5 - change * 5.0 + max(0.0, volume - 1.0) * 0.15))
    warnings = ["historical_flow_not_available"]
    return AnalyzerResult(
        analyzer="distribution", score=score, confidence=0.45,
        metrics={"price_change": change, "volume_ratio": volume}, warnings=warnings,
    )
