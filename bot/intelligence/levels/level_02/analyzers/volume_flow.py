import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result


def _positive_finite(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and value > 0
    )


def analyze(snapshot: MarketSnapshot, level1: Level1Result) -> AnalyzerResult:
    base_result = next((r for r in level1.analyzer_results if r.analyzer == "volume"), None)
    change = snapshot.price_change()

    # Prefer an already calculated ratio from the real candle/context producer.
    # Fall back only to observed current/average volume pairs.
    ratio = snapshot.volume_ratio
    ratio_source = "volume_ratio"
    if not _positive_finite(ratio):
        ratio = None
        candidates = (
            (snapshot.volume, snapshot.average_volume, "volume/average_volume"),
            (snapshot.candle_volume, snapshot.average_candle_volume, "candle_volume/average_candle_volume"),
        )
        for current, average, source in candidates:
            if _positive_finite(current) and _positive_finite(average):
                candidate = current / average
                if math.isfinite(candidate) and candidate > 0:
                    ratio, ratio_source = candidate, source
                    break

    if base_result is None or base_result.confidence <= 0 or change is None or ratio is None:
        return AnalyzerResult(
            "volume_flow",
            0.0,
            0.0,
            {"ratio": ratio, "ratio_source": ratio_source if ratio is not None else None, "change": change},
            ("insufficient_volume_history",),
        )

    if change > 0:
        confirmation = min(max(0.5 + (ratio - 1.0) * 0.5, 0.0), 1.0)
    elif change < 0:
        confirmation = min(max(0.5 - (ratio - 1.0) * 0.5, 0.0), 1.0)
    else:
        # No directional price move: volume cannot confirm either direction.
        confirmation = 0.5

    score = 0.5 * base_result.score + 0.5 * confirmation
    confidence = min(base_result.confidence, level1.confidence)
    return AnalyzerResult(
        "volume_flow",
        score,
        confidence,
        {"ratio": ratio, "ratio_source": ratio_source, "confirmation": confirmation, "change": change},
    )
