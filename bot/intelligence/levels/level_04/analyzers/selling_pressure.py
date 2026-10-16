import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def _volume_ratio(snapshot: MarketSnapshot):
    ratio = snapshot.volume_ratio
    if ratio is None and snapshot.volume is not None and snapshot.average_volume is not None:
        if snapshot.average_volume > 0 and snapshot.volume >= 0:
            ratio = snapshot.volume / snapshot.average_volume
    if ratio is not None and (
        not isinstance(ratio, (int, float)) or not math.isfinite(ratio) or ratio < 0
    ):
        return None
    return ratio


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    change = snapshot.price_change()
    if change is None:
        return AnalyzerResult("selling_pressure", 0.0, 0.0, {}, ("price_change_not_available",))
    volume_ratio = _volume_ratio(snapshot)
    close_position = snapshot.close_position
    if close_position is not None and (
        not isinstance(close_position, (int, float)) or not math.isfinite(close_position)
        or not 0.0 <= close_position <= 1.0
    ):
        close_position = None

    directional_score = max(0.0, min(1.0, 0.5 - change * 8.0))
    if close_position is not None:
        directional_score = 0.65 * directional_score + 0.35 * (1.0 - close_position)
    confidence = min(1.0, 0.55 + 0.25 * (volume_ratio is not None) + 0.20 * (close_position is not None))
    warnings = () if volume_ratio is not None and close_position is not None else ("selling_pressure_partial_inputs",)
    return AnalyzerResult(
        "selling_pressure", directional_score, confidence,
        {"price_change": change, "volume_ratio": volume_ratio, "close_position": close_position}, warnings,
    )
