"""Long-only Markowitz mean-variance portfolio optimization.

Pure recommendation engine: estimates minimum-variance or target-return
weights from aligned historical returns. It never places or changes orders.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class MarkowitzResult:
    assets: tuple[str, ...]
    weights: dict[str, float]
    expected_return: float
    expected_volatility: float
    objective: str
    observation_count: int
    warnings: tuple[str, ...] = ()


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    """Gaussian elimination with partial pivoting; return None if singular."""
    n = len(vector)
    augmented = [list(matrix[i]) + [vector[i]] for i in range(n)]
    for column in range(n):
        pivot = max(range(column, n), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-14:
            return None
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        for j in range(column, n + 1):
            augmented[column][j] /= divisor
        for row in range(n):
            if row == column:
                continue
            factor = augmented[row][column]
            for j in range(column, n + 1):
                augmented[row][j] -= factor * augmented[column][j]
    return [augmented[i][n] for i in range(n)]


def _project_simplex(values: list[float]) -> list[float]:
    """Euclidean projection onto non-negative weights summing to one."""
    ordered = sorted(values, reverse=True)
    cumulative = 0.0
    rho = 0
    for index, value in enumerate(ordered, start=1):
        cumulative += value
        if value - (cumulative - 1.0) / index > 0.0:
            rho = index
    if rho == 0:
        return [1.0 / len(values)] * len(values)
    theta = (sum(ordered[:rho]) - 1.0) / rho
    projected = [max(value - theta, 0.0) for value in values]
    total = sum(projected)
    return [value / total for value in projected]


def _project_capped_simplex(values: list[float], cap: float) -> list[float]:
    """Project onto weights in [0, cap] whose sum is exactly one."""
    if len(values) * cap < 1.0 - 1e-12:
        raise ValueError("cap makes a fully-invested portfolio impossible")
    low = min(values) - cap
    high = max(values)
    for _ in range(100):
        threshold = (low + high) / 2.0
        total = sum(min(cap, max(0.0, value - threshold)) for value in values)
        if total > 1.0:
            low = threshold
        else:
            high = threshold
    projected = [min(cap, max(0.0, value - (low + high) / 2.0)) for value in values]
    total = sum(projected)
    if total <= 0.0:
        return [1.0 / len(values)] * len(values)
    return [value / total for value in projected]


def optimize_markowitz(
    asset_returns: Mapping[str, Sequence[float]],
    *,
    objective: str = "minimum_variance",
    target_return: float | None = None,
    max_weight: float = 1.0,
    risk_aversion: float = 1.0,
    annualization_factor: int = 1,
    max_iterations: int = 20_000,
    tolerance: float = 1e-10,
) -> MarkowitzResult:
    """Optimize long-only fully-invested weights using projected gradient.

    Inputs are aligned chronological fractional returns at equal intervals.
    Objective is minimum_variance or mean_variance. The latter maximizes
    mean return minus risk_aversion times variance. For a target return,
    the minimum-variance objective adds a penalty for falling below target;
    feasibility is checked on the best found portfolio. No short selling or
    leverage is allowed. Results are estimates, not guaranteed optima.
    """
    if not isinstance(asset_returns, Mapping) or not asset_returns:
        raise ValueError("asset_returns must be a non-empty mapping")
    if objective not in ("minimum_variance", "mean_variance"):
        raise ValueError("unsupported objective")
    for name, value in (("max_weight", max_weight), ("risk_aversion", risk_aversion), ("tolerance", tolerance)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if not 0.0 < max_weight <= 1.0:
        raise ValueError("max_weight must be in (0, 1]")
    if risk_aversion <= 0.0 or tolerance <= 0.0:
        raise ValueError("risk_aversion and tolerance must be positive")
    if isinstance(annualization_factor, bool) or not isinstance(annualization_factor, int) or annualization_factor <= 0:
        raise ValueError("annualization_factor must be a positive integer")
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations <= 0:
        raise ValueError("max_iterations must be a positive integer")
    if target_return is not None and (isinstance(target_return, bool) or not isinstance(target_return, (int, float)) or not math.isfinite(target_return)):
        raise ValueError("target_return must be finite or None")

    assets = list(asset_returns.keys())
    series_matrix: list[list[float]] = []
    count = None
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
        if count is None:
            count = len(values)
        elif len(values) != count:
            raise ValueError("asset return series must be equally long and aligned")
        series_matrix.append(values)
    if count is None or count < 2:
        raise ValueError("at least two aligned return observations are required")
    if len(assets) * max_weight < 1.0 - 1e-12:
        raise ValueError("max_weight makes a fully-invested portfolio impossible")

    means = [sum(values) / count for values in series_matrix]
    centered = [[value - means[i] for value in series_matrix[i]] for i in range(len(assets))]
    covariance = [[0.0 for _ in assets] for _ in assets]
    for i in range(len(assets)):
        for j in range(len(assets)):
            covariance[i][j] = sum(a * b for a, b in zip(centered[i], centered[j])) / (count - 1)

    n = len(assets)
    # A conservative Lipschitz bound for the covariance gradient.
    max_row_sum = max(sum(abs(value) for value in row) for row in covariance)
    step = 1.0 / max(2.0 * max_row_sum * annualization_factor * max(risk_aversion, 1.0), 1e-12)
    weights = [1.0 / n] * n
    warnings = []
    for _ in range(max_iterations):
        cov_w = [sum(covariance[i][j] * weights[j] for j in range(n)) for i in range(n)]
        if objective == "mean_variance":
            gradient = [2.0 * risk_aversion * annualization_factor * cov_w[i] - means[i] * annualization_factor for i in range(n)]
        else:
            gradient = [2.0 * annualization_factor * cov_w[i] for i in range(n)]
            if target_return is not None:
                current_return = sum(means[i] * weights[i] for i in range(n)) * annualization_factor
                shortfall = max(0.0, float(target_return) - current_return)
                if shortfall > 0.0:
                    penalty = 10.0
                    gradient = [gradient[i] - 2.0 * penalty * shortfall * means[i] * annualization_factor for i in range(n)]
        candidate = _project_capped_simplex(
            [weights[i] - step * gradient[i] for i in range(n)],
            max_weight,
        )
        delta = max(abs(candidate[i] - weights[i]) for i in range(n))
        weights = candidate
        if delta < tolerance:
            break
    else:
        warnings.append("optimizer_reached_iteration_limit")

    expected_return = sum(means[i] * weights[i] for i in range(n)) * annualization_factor
    variance = sum(weights[i] * covariance[i][j] * weights[j] for i in range(n) for j in range(n)) * annualization_factor
    volatility = math.sqrt(max(0.0, variance))
    if target_return is not None:
        warnings.append("target_return_is_soft_penalty_not_hard_constraint")
        if expected_return + 1e-8 < target_return:
            warnings.append("target_return_not_reached")
    return MarkowitzResult(
        assets=tuple(assets),
        weights={asset: weights[i] for i, asset in enumerate(assets)},
        expected_return=expected_return,
        expected_volatility=volatility,
        objective=objective,
        observation_count=count,
        warnings=tuple(warnings),
    )
