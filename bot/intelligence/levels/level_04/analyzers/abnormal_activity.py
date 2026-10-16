import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    volume_ratio = snapshot.volume_ratio
    if volume_ratio is None and snapshot.volume is not None and snapshot.average_volume is not None:
        if snapshot.average_volume > 0 and snapshot.volume >= 0:
            volume_ratio = snapshot.volume / snapshot.average_volume
    if volume_ratio is not None and (
        not isinstance(volume_ratio, (int, float)) or not math.isfinite(volume_ratio) or volume_ratio < 0
    ):
        volume_ratio = None

    volatility = snapshot.volatility
    if volatility is not None and (
        not isinstance(volatility, (int, float)) or not math.isfinite(volatility) or volatility < 0
    ):
        volatility = None

    if volume_ratio is None and volatility is None:
        return AnalyzerResult("abnormal_activity", 0.0, 0.0, {}, ("volume_and_volatility_unavailable",))

    volume_component = max(0.0, volume_ratio - 1.0) / 3.0 if volume_ratio is not None else 0.0
    volatility_component = min(1.0, volatility * 10.0) * 0.35 if volatility is not None else 0.0
    score = min(1.0, max(0.0, volume_component + volatility_component))
    confidence = 0.75 if volume_ratio is not None and volatility is not None else 0.5
    warnings = ()
    if volume_ratio is None or volatility is None:
        warnings = ("abnormal_activity_partial_inputs",)
    return AnalyzerResult(
        "abnormal_activity", score, confidence,
        {"volume_ratio": volume_ratio, "volatility": volatility}, warnings,
    )
