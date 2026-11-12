"""Euler decomposition of portfolio volatility into asset risk contributions.

This pure analytics module accepts aligned periodic returns and long-only weights.
It is diagnostic only and is not connected to trade authorization.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class AssetRiskContribution:
    asset: str
    weight_pct: float
    marginal_risk: float | None
    component_risk: float | None
    contribution_pct: float | None


@dataclass(frozen=True)
class EulerRiskContributionResult:
    observation_count: int
    portfolio_volatility: float | None
    assets: tuple[AssetRiskContribution, ...]
    contribution_sum_pct: float | None
    warnings: tuple[str, ...] = ()


def calculate_euler_risk_contribution(
    asset_returns: Mapping[str, Sequence[float]],
    weights: Mapping[str, float],
) -> EulerRiskContributionResult:
    """Decompose portfolio standard deviation using Euler contributions.

    Returns must be chronological, equally spaced fractional returns aligned
    across all assets. Weights are non-negative portfolio weights; they are
    normalized to sum to one. Sample covariance (n-1 denominator) is used.
    """
    if not isinstance(asset_returns, Mapping) or not isinstance(weights, Mapping):
        raise ValueError("asset_returns and weights must be mappings")
    if not asset_returns or not weights:
        raise ValueError("asset_returns and weights must not be empty")
    if set(asset_returns) != set(weights):
        raise ValueError("asset_returns and weights must contain identical asset keys")

    assets = list(asset_returns.keys())
    matrix: list[list[float]] = []
    observation_count = None
    for asset in assets:
        if not isinstance(asset, str) or not asset.strip():
            raise ValueError("asset names must be non-empty strings")
        series = asset_returns[asset]
        if isinstance(series, (str, bytes)) or not isinstance(series, Sequence):
            raise ValueError("each asset return series must be a sequence")
        values = []
        for raw in series:
            if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw) or raw <= -1.0:
                raise ValueError("returns must be finite numbers greater than -1")
            values.append(float(raw))
        if observation_count is None:
            observation_count = len(values)
        elif len(values) != observation_count:
            raise ValueError("all asset return series must have equal lengths and aligned timestamps")
        matrix.append(values)

    if observation_count is None or observation_count < 2:
        return EulerRiskContributionResult(
            observation_count or 0, None, (), None, ("insufficient_aligned_return_history",)
        )

    raw_weights = []
    for asset in assets:
        weight = weights[asset]
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight < 0.0:
            raise ValueError("weights must be finite non-negative numbers")
        raw_weights.append(float(weight))
    weight_total = sum(raw_weights)
    if not math.isfinite(weight_total) or weight_total <= 0.0:
        raise ValueError("at least one portfolio weight must be positive")
    normalized = [weight / weight_total for weight in raw_weights]

    means = [sum(series) / observation_count for series in matrix]
    centered = [[value - means[i] for value in matrix[i]] for i in range(len(assets))]
    covariance = [[0.0 for _ in assets] for _ in assets]
    for i in range(len(assets)):
        for j in range(len(assets)):
            covariance[i][j] = sum(a * b for a, b in zip(centered[i], centered[j])) / (observation_count - 1)

    covariance_times_weights = [
        sum(covariance[i][j] * normalized[j] for j in range(len(assets)))
        for i in range(len(assets))
    ]
    variance = sum(normalized[i] * covariance_times_weights[i] for i in range(len(assets)))
    if variance < 0.0 and abs(variance) < 1e-15:
        variance = 0.0
    if not math.isfinite(variance) or variance < 0.0:
        raise ValueError("portfolio variance is invalid")
    volatility = math.sqrt(variance)

    if volatility == 0.0:
        contributions = tuple(
            AssetRiskContribution(asset, normalized[i] * 100.0, None, None, None)
            for i, asset in enumerate(assets)
        )
        return EulerRiskContributionResult(
            observation_count, 0.0, contributions, None, ("zero_portfolio_volatility",)
        )

    contributions = []
    for i, asset in enumerate(assets):
        marginal = covariance_times_weights[i] / volatility
        component = normalized[i] * marginal
        contributions.append(AssetRiskContribution(
            asset=asset,
            weight_pct=normalized[i] * 100.0,
            marginal_risk=marginal,
            component_risk=component,
            contribution_pct=component / volatility * 100.0,
        ))
    contribution_sum = sum(item.contribution_pct for item in contributions if item.contribution_pct is not None)
    return EulerRiskContributionResult(
        observation_count=observation_count,
        portfolio_volatility=volatility,
        assets=tuple(contributions),
        contribution_sum_pct=contribution_sum,
        warnings=(),
    )
