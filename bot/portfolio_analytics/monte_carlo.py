"""Monte Carlo scenario analysis using circular moving-block bootstrap.

Historical period returns are resampled in contiguous blocks to retain some
serial dependence. Results are scenario distributions, not forecasts.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import random
from collections.abc import Sequence


@dataclass(frozen=True)
class MonteCarloResult:
    simulation_count: int
    horizon: int
    block_length: int
    median_return_pct: float | None
    percentile_05_return_pct: float | None
    percentile_25_return_pct: float | None
    percentile_75_return_pct: float | None
    percentile_95_return_pct: float | None
    probability_of_loss_pct: float | None
    median_max_drawdown_pct: float | None
    percentile_95_max_drawdown_pct: float | None
    warnings: tuple[str, ...] = ()


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _simulate_path(
    historical_returns: list[float], horizon: int, block_length: int, rng: random.Random
) -> tuple[float, float]:
    sampled: list[float] = []
    history_size = len(historical_returns)
    while len(sampled) < horizon:
        start = rng.randrange(history_size)
        take = min(block_length, horizon - len(sampled))
        sampled.extend(historical_returns[(start + offset) % history_size] for offset in range(take))

    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for period_return in sampled:
        equity *= 1.0 + period_return
        peak = max(peak, equity)
        if peak > 0.0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
    return (equity - 1.0) * 100.0, max_drawdown * 100.0


def monte_carlo_block_bootstrap(
    historical_returns: Sequence[float],
    *,
    simulations: int = 2000,
    horizon: int | None = None,
    block_length: int | None = None,
    seed: int | None = None,
) -> MonteCarloResult:
    """Simulate compounded return and drawdown distributions from period returns.

    Returns must be chronological, equally spaced fractional returns (0.01 = 1%).
    Circular blocks are sampled with replacement. A fixed seed makes runs
    reproducible. At least two historical observations are required.
    """
    if isinstance(simulations, bool) or not isinstance(simulations, int) or not 1 <= simulations <= 100_000:
        raise ValueError("simulations must be an integer between 1 and 100000")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise ValueError("seed must be an integer or None")

    values: list[float] = []
    for value in historical_returns:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= -1.0:
            raise ValueError("historical returns must be finite numbers greater than -1")
        values.append(float(value))

    actual_horizon = len(values) if horizon is None else horizon
    if isinstance(actual_horizon, bool) or not isinstance(actual_horizon, int) or actual_horizon <= 0:
        raise ValueError("horizon must be a positive integer")
    actual_block = min(5, len(values)) if block_length is None else block_length
    if isinstance(actual_block, bool) or not isinstance(actual_block, int) or actual_block <= 0:
        raise ValueError("block_length must be a positive integer")
    if values and actual_block > len(values):
        raise ValueError("block_length cannot exceed the number of historical returns")

    if len(values) < 2:
        return MonteCarloResult(
            simulations, actual_horizon, actual_block, None, None, None, None, None,
            None, None, None, ("insufficient_historical_returns",)
        )

    rng = random.Random(seed)
    path_returns: list[float] = []
    path_drawdowns: list[float] = []
    for _ in range(simulations):
        terminal_return, max_drawdown = _simulate_path(values, actual_horizon, actual_block, rng)
        path_returns.append(terminal_return)
        path_drawdowns.append(max_drawdown)

    return MonteCarloResult(
        simulation_count=simulations,
        horizon=actual_horizon,
        block_length=actual_block,
        median_return_pct=_percentile(path_returns, 0.50),
        percentile_05_return_pct=_percentile(path_returns, 0.05),
        percentile_25_return_pct=_percentile(path_returns, 0.25),
        percentile_75_return_pct=_percentile(path_returns, 0.75),
        percentile_95_return_pct=_percentile(path_returns, 0.95),
        probability_of_loss_pct=sum(value < 0.0 for value in path_returns) / simulations * 100.0,
        median_max_drawdown_pct=_percentile(path_drawdowns, 0.50),
        percentile_95_max_drawdown_pct=_percentile(path_drawdowns, 0.95),
        warnings=(),
    )
