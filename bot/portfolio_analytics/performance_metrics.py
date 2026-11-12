"""Risk-adjusted metrics for chronological portfolio equity curves.

This module is pure and diagnostic; it never authorizes or executes trades.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PortfolioRiskMetrics:
    observation_count: int
    return_count: int
    cumulative_return_pct: float | None
    annualized_return_pct: float | None
    annualized_volatility_pct: float | None
    downside_deviation_pct: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None
    max_drawdown_pct: float | None
    warnings: tuple[str, ...] = ()


def calculate_performance_metrics(
    equity_curve: Sequence[float],
    *,
    periods_per_year: int = 252,
    annual_risk_free_rate: float = 0.0,
    annual_target_return: float = 0.0,
) -> PortfolioRiskMetrics:
    """Calculate annualized Sharpe/Sortino and drawdown from equity observations.

    The curve must be oldest-to-newest and sampled at equally spaced intervals.
    Rates are annual effective rates and are converted to per-period rates.
    """
    if isinstance(periods_per_year, bool) or not isinstance(periods_per_year, int) or periods_per_year <= 0:
        raise ValueError("periods_per_year must be a positive integer")
    for name, value in (("annual_risk_free_rate", annual_risk_free_rate), ("annual_target_return", annual_target_return)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
        if value <= -1.0:
            raise ValueError(f"{name} must be greater than -1")

    values = []
    for value in equity_curve:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError("equity_curve values must be finite positive numbers")
        values.append(float(value))

    if not values:
        return PortfolioRiskMetrics(0, 0, None, None, None, None, None, None, None, ("insufficient_equity_observations",))

    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, (peak - value) / peak)

    if len(values) < 2:
        return PortfolioRiskMetrics(len(values), 0, None, None, None, None, None, None, max_drawdown * 100.0, ("insufficient_equity_observations",))

    returns = [current / previous - 1.0 for previous, current in zip(values, values[1:])]
    cumulative_return = values[-1] / values[0] - 1.0
    annualized_return = (values[-1] / values[0]) ** (periods_per_year / len(returns)) - 1.0
    rf_period = (1.0 + float(annual_risk_free_rate)) ** (1.0 / periods_per_year) - 1.0
    target_period = (1.0 + float(annual_target_return)) ** (1.0 / periods_per_year) - 1.0
    excess = [value - rf_period for value in returns]
    mean_excess = sum(excess) / len(excess)
    warnings = []

    if len(excess) > 1:
        variance = sum((value - mean_excess) ** 2 for value in excess) / (len(excess) - 1)
        volatility = math.sqrt(variance)
    else:
        volatility = 0.0
        warnings.append("insufficient_returns_for_volatility")

    downside_squares = [min(value - target_period, 0.0) ** 2 for value in returns]
    downside_deviation = math.sqrt(sum(downside_squares) / len(downside_squares))
    sharpe = mean_excess / volatility * math.sqrt(periods_per_year) if volatility > 0 else None
    sortino = None
    if downside_deviation > 0:
        mean_target_excess = sum(value - target_period for value in returns) / len(returns)
        sortino = mean_target_excess / downside_deviation * math.sqrt(periods_per_year)
    if sharpe is None:
        warnings.append("zero_return_volatility")
    if sortino is None:
        warnings.append("zero_downside_deviation")

    return PortfolioRiskMetrics(
        observation_count=len(values),
        return_count=len(returns),
        cumulative_return_pct=cumulative_return * 100.0,
        annualized_return_pct=annualized_return * 100.0,
        annualized_volatility_pct=volatility * math.sqrt(periods_per_year) * 100.0,
        downside_deviation_pct=downside_deviation * math.sqrt(periods_per_year) * 100.0,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown_pct=max_drawdown * 100.0,
        warnings=tuple(warnings),
    )
