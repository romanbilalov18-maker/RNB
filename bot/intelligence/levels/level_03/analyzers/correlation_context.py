from math import sqrt

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


def _pearson(left: tuple[float, ...], right: tuple[float, ...]) -> float | None:
    pairs = list(zip(left, right))
    if len(pairs) < 10:
        return None
    x = [item[0] for item in pairs]
    y = [item[1] for item in pairs]
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    dx = [value - mean_x for value in x]
    dy = [value - mean_y for value in y]
    denom = sqrt(sum(value * value for value in dx) * sum(value * value for value in dy))
    if denom == 0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / denom


def analyze(snapshot: MarketSnapshot, level2: Level2Result) -> AnalyzerResult:
    correlation = _pearson(snapshot.correlation_asset_returns, snapshot.market_return_history)
    if correlation is None:
        return AnalyzerResult(
            "correlation_context", 0.0, 0.0,
            {"observations": min(len(snapshot.correlation_asset_returns), len(snapshot.market_return_history))},
            ("cross_asset_history_insufficient",),
        )
    score = max(0.0, min(1.0, (correlation + 1.0) / 2.0))
    confidence = min(1.0, min(len(snapshot.correlation_asset_returns), len(snapshot.market_return_history)) / 30.0)
    return AnalyzerResult(
        "correlation_context", score, confidence,
        {"pearson_correlation": correlation,
         "observations": min(len(snapshot.historical_returns), len(snapshot.market_return_history))},
    )
