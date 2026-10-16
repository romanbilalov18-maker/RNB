import math
from collections.abc import Sequence
from math import sqrt

from bot.intelligence.core.models.analysis_result import AnalyzerResult


def _dated_returns(dates: Sequence, returns: Sequence) -> tuple[dict, bool]:
    """Pair only explicitly aligned, finite observations; report shape mismatch."""
    if len(dates) != len(returns):
        return {}, True
    paired = {}
    for day, raw_value in zip(dates, returns):
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if day is not None and math.isfinite(value):
            paired[day] = value
    return paired, False


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
    if denominator <= 0 or not math.isfinite(denominator):
        return None
    result = sum(a * b for a, b in zip(left_delta, right_delta)) / denominator
    return result if math.isfinite(result) else None


def analyze(snapshot, level8_result, level6_result) -> AnalyzerResult:
    positions = getattr(snapshot, "portfolio_positions", ())
    if not positions:
        if getattr(snapshot, "portfolio_context_available", False):
            return AnalyzerResult(
                "correlation_risk", 0.0, 0.0,
                {"position_count": 0, "positions_with_valid_history": 0, "weighted_absolute_correlation": 0.0},
                ["portfolio_confirmed_empty", "portfolio_correlation_not_applicable"],
            )
        return AnalyzerResult("correlation_risk", 0.0, 0.0, {"position_count": 0}, ["portfolio_positions_not_available"])

    candidate, candidate_mismatch = _dated_returns(
        getattr(snapshot, "historical_return_dates", ()),
        getattr(snapshot, "historical_returns", ()),
    )
    correlations = []
    mismatched_histories = int(candidate_mismatch)
    for position in positions:
        if position.get("symbol") == snapshot.symbol:
            continue
        held, mismatch = _dated_returns(
            position.get("historical_return_dates", ()),
            position.get("historical_returns", ()),
        )
        mismatched_histories += int(mismatch)
        shared_dates = sorted(set(candidate).intersection(held))
        pairs = [(candidate[day], held[day]) for day in shared_dates]
        correlation = _pearson(pairs)
        try:
            value = float(position.get("market_value", 0.0))
        except (TypeError, ValueError):
            continue
        if correlation is not None and math.isfinite(value) and value > 0:
            correlations.append((abs(correlation), value, len(pairs), position.get("symbol")))

    if not correlations:
        warnings = ["portfolio_correlation_history_insufficient"]
        if mismatched_histories:
            warnings.append("portfolio_return_dates_values_misaligned")
        return AnalyzerResult(
            "correlation_risk", 0.0, 0.0,
            {"position_count": len(positions), "positions_with_valid_history": 0, "misaligned_histories": mismatched_histories},
            warnings,
        )
    total_value = sum(value for _, value, _, _ in correlations)
    weighted_correlation = sum(correlation * value for correlation, value, _, _ in correlations) / total_value
    score = max(0.0, min(1.0, weighted_correlation))
    coverage = len(correlations) / max(1, len(positions) - sum(1 for p in positions if p.get("symbol") == snapshot.symbol))
    history_confidence = min(1.0, min(count for _, _, count, _ in correlations) / 30.0)
    confidence = min(1.0, coverage * history_confidence)
    warnings = []
    if coverage < 1.0:
        warnings.append("some_portfolio_correlations_unavailable")
    if mismatched_histories:
        warnings.append("portfolio_return_dates_values_misaligned")
        confidence *= max(0.0, 1.0 - mismatched_histories / max(1, len(positions) + 1))
    return AnalyzerResult(
        "correlation_risk", score, max(0.0, min(1.0, confidence)),
        {
            "weighted_absolute_correlation": weighted_correlation,
            "position_correlations": {symbol: correlation for correlation, _, _, symbol in correlations},
            "positions_with_valid_history": len(correlations),
            "position_count": len(positions),
            "misaligned_histories": mismatched_histories,
        },
        warnings,
    )
