import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    liquidity = snapshot.liquidity
    if liquidity is None or not isinstance(liquidity, (int, float)) or not math.isfinite(liquidity):
        return AnalyzerResult("liquidity_behavior", 0.0, 0.0, {}, ("liquidity_data_not_available",))
    if not 0.0 <= liquidity <= 1.0:
        return AnalyzerResult(
            "liquidity_behavior", 0.0, 0.0, {"raw_liquidity": liquidity},
            ("liquidity_value_out_of_range",),
        )

    volume_ratio = snapshot.volume_ratio
    if volume_ratio is None and snapshot.volume is not None and snapshot.average_volume is not None:
        if snapshot.average_volume > 0 and snapshot.volume >= 0:
            volume_ratio = snapshot.volume / snapshot.average_volume
    if volume_ratio is not None and (
        not isinstance(volume_ratio, (int, float)) or not math.isfinite(volume_ratio) or volume_ratio < 0
    ):
        volume_ratio = None

    if volume_ratio is None:
        return AnalyzerResult(
            "liquidity_behavior", liquidity, 0.5,
            {"liquidity": liquidity, "volume_ratio": None}, ("liquidity_volume_context_unavailable",),
        )
    score = min(1.0, max(0.0, liquidity * 0.7 + min(1.0, volume_ratio / 2.0) * 0.3))
    return AnalyzerResult(
        "liquidity_behavior", score, 0.8,
        {"liquidity": liquidity, "volume_ratio": volume_ratio},
    )
