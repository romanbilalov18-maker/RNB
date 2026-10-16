import math
from math import sqrt

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


def _pearson(left: tuple[float, ...], right: tuple[float, ...]) -> tuple[float | None, int, int]:
    # Pair observations by timestamp/order and exclude invalid numeric values.
    pairs = []
    for x, y in zip(left, right):
        if (
            isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
            or isinstance(y, bool) or not isinstance(y, (int, float)) or not math.isfinite(y)
        ):
            continue
        pairs.append((float(x), float(y)))
    if len(pairs) < 10:
        return None, len(pairs), len(left) + len(right) - 2 * len(pairs)
    x = [item[0] for item in pairs]
    y = [item[1] for item in pairs]
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    dx = [value - mean_x for value in x]
    dy = [value - mean_y for value in y]
    denom = sqrt(sum(value * value for value in dx) * sum(value * value for value in dy))
    if denom == 0 or not math.isfinite(denom):
        return None, len(pairs), len(left) + len(right) - 2 * len(pairs)
    value = sum(a * b for a, b in zip(dx, dy)) / denom
    if not math.isfinite(value):
        return None, len(pairs), len(left) + len(right) - 2 * len(pairs)
    return max(-1.0, min(1.0, value)), len(pairs), len(left) + len(right) - 2 * len(pairs)


def analyze(snapshot: MarketSnapshot, level2: Level2Result) -> AnalyzerResult:
    correlation, observations, invalid_count = _pearson(
        snapshot.correlation_asset_returns, snapshot.market_return_history
    )
    if correlation is None:
        return AnalyzerResult(
            "correlation_context", 0.0, 0.0,
            {"observations": observations, "invalid_or_unpaired_observations": invalid_count},
            ("cross_asset_history_insufficient_or_invalid",),
        )
    score = (correlation + 1.0) / 2.0
    confidence = min(1.0, observations / 30.0)
    warnings = []
    if snapshot.correlation_benchmark == "scanned_peer_basket":
        warnings.append("correlation_uses_scanned_peer_basket")
    if invalid_count:
        warnings.append("correlation_invalid_or_unpaired_observations_excluded")
    return AnalyzerResult(
        "correlation_context", score, confidence,
        {
            "pearson_correlation": correlation,
            "observations": observations,
            "invalid_or_unpaired_observations": invalid_count,
            "benchmark_source": snapshot.correlation_benchmark or "unspecified",
        },
        tuple(warnings),
    )
