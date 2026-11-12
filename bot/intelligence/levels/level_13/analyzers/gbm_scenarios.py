"""Geometric Brownian Motion scenario sampler for price paths.

This module produces model-based price scenarios from supplied drift and
volatility estimates. It is diagnostic only and never authorizes trades.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import random


@dataclass(frozen=True)
class GBMScenarioResult:
    initial_price: float
    horizon_steps: int
    simulation_count: int
    expected_terminal_price: float
    median_terminal_price: float
    percentile_05_terminal_price: float
    percentile_95_terminal_price: float
    probability_below_initial_pct: float
    median_max_drawdown_pct: float
    percentile_95_max_drawdown_pct: float
    warnings: tuple[str, ...] = ()


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def simulate_gbm_scenarios(
    initial_price: float,
    annual_drift: float,
    annual_volatility: float,
    *,
    horizon_steps: int = 252,
    steps_per_year: int = 252,
    simulations: int = 5000,
    seed: int | None = None,
) -> GBMScenarioResult:
    """Simulate GBM price paths and summarize terminal and drawdown risk.

    Drift and volatility are annualized decimal parameters. The discrete
    update is S[t+1] = S[t] * exp((mu - sigma^2/2)dt + sigma*sqrt(dt)*Z).
    """
    for name, value in (
        ("initial_price", initial_price),
        ("annual_drift", annual_drift),
        ("annual_volatility", annual_volatility),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if initial_price <= 0.0:
        raise ValueError("initial_price must be positive")
    if annual_volatility < 0.0:
        raise ValueError("annual_volatility must be non-negative")
    if isinstance(horizon_steps, bool) or not isinstance(horizon_steps, int) or horizon_steps <= 0:
        raise ValueError("horizon_steps must be a positive integer")
    if isinstance(steps_per_year, bool) or not isinstance(steps_per_year, int) or steps_per_year <= 0:
        raise ValueError("steps_per_year must be a positive integer")
    if isinstance(simulations, bool) or not isinstance(simulations, int) or not 1 <= simulations <= 100_000:
        raise ValueError("simulations must be an integer between 1 and 100000")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise ValueError("seed must be an integer or None")

    rng = random.Random(seed)
    dt = 1.0 / steps_per_year
    drift_step = (annual_drift - 0.5 * annual_volatility ** 2) * dt
    diffusion_step = annual_volatility * math.sqrt(dt)
    terminal_prices = []
    max_drawdowns = []
    for _ in range(simulations):
        price = float(initial_price)
        peak = price
        max_drawdown = 0.0
        for _step in range(horizon_steps):
            price *= math.exp(drift_step + diffusion_step * rng.gauss(0.0, 1.0))
            peak = max(peak, price)
            max_drawdown = max(max_drawdown, (peak - price) / peak)
        terminal_prices.append(price)
        max_drawdowns.append(max_drawdown * 100.0)

    horizon_years = horizon_steps / steps_per_year
    expected_terminal = initial_price * math.exp(annual_drift * horizon_years)
    return GBMScenarioResult(
        initial_price=float(initial_price),
        horizon_steps=horizon_steps,
        simulation_count=simulations,
        expected_terminal_price=expected_terminal,
        median_terminal_price=_percentile(terminal_prices, 0.50),
        percentile_05_terminal_price=_percentile(terminal_prices, 0.05),
        percentile_95_terminal_price=_percentile(terminal_prices, 0.95),
        probability_below_initial_pct=sum(price < initial_price for price in terminal_prices) / simulations * 100.0,
        median_max_drawdown_pct=_percentile(max_drawdowns, 0.50),
        percentile_95_max_drawdown_pct=_percentile(max_drawdowns, 0.95),
        warnings=("zero_volatility_deterministic_paths",) if annual_volatility == 0.0 else (),
    )
