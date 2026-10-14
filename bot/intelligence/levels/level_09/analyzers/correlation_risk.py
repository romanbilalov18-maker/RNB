from math import sqrt

from bot.intelligence.core.models.analysis_result import AnalyzerResult


def _pearson(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 10:
        return None
    left = [pair[0] for pair in pairs]
    right = [pair[1] for pair in pairs]
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    left_delta = [value - left_mean for value in left]
    right_delta = [value - right_mean for value in right]
    denominator = sqrt(sum(value * value for value in left_delta) * sum(value * value for value in right_delta))
    if denominator <= 0:
        return None
    return sum(a * b for a, b in zip(left_delta, right_delta)) / denominator


def analyze(snapshot, level8_result, level6_result) -> AnalyzerResult:
    positions = getattr(snapshot, "portfolio_positions", ())
    if not positions:
        if getattr(snapshot, "portfolio_context_available", False):
            return AnalyzerResult(
                "correlation_risk", 0.0, 1.0,
                {"position_count": 0, "positions_with_valid_history": 0, "weighted_absolute_correlation": 0.0},
                ["portfolio_confirmed_empty"],
            )
        return AnalyzerResult("correlation_risk", 0.0, 0.0, {"position_count": 0}, ["portfolio_positions_not_available"])
    candidate = dict(zip(snapshot.historical_return_dates, snapshot.historical_returns))
    correlations = []
    for position in positions:
        if position.get("symbol") == snapshot.symbol:
            continue
        dates = position.get("historical_return_dates", ())
        returns = position.get("historical_returns", ())
        held = dict(zip(dates, returns))
        shared_dates = sorted(set(candidate).intersection(held))
        pairs = [(candidate[day], held[day]) for day in shared_dates]
        correlation = _pearson(pairs)
        value = max(0.0, float(position.get("market_value", 0.0)))
        if correlation is not None and value > 0:
            correlations.append((abs(correlation), value, len(pairs), position.get("symbol")))
    if not correlations:
        return AnalyzerResult("correlation_risk", 0.0, 0.0, {"position_count": len(positions)}, ["portfolio_correlation_history_insufficient"])
    total_value = sum(value for _, value, _, _ in correlations)
    weighted_correlation = sum(correlation * value for correlation, value, _, _ in correlations) / total_value
    score = max(0.0, min(1.0, weighted_correlation))
    coverage = len(correlations) / len(positions)
    history_confidence = min(1.0, min(count for _, _, count, _ in correlations) / 30.0)
    confidence = min(1.0, coverage * history_confidence)
    return AnalyzerResult(
        "correlation_risk", score, confidence,
        {"weighted_absolute_correlation": weighted_correlation,
         "position_correlations": {symbol: correlation for correlation, _, _, symbol in correlations},
         "positions_with_valid_history": len(correlations), "position_count": len(positions)},
        () if coverage >= 1.0 else ("some_portfolio_correlations_unavailable",),
    )
