"""Conservative fractional Kelly sizing calculator.

This pure recommendation utility estimates a bankroll fraction from an
estimated win probability and average win/loss magnitudes. It does not
connect to portfolio execution or authorize trades.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class FractionalKellyResult:
    win_probability: float
    average_win: float
    average_loss: float
    full_kelly_fraction: float
    applied_fraction: float
    recommended_capital_fraction: float
    recommended_capital_pct: float
    expected_edge: float
    warnings: tuple[str, ...] = ()


def calculate_fractional_kelly(
    win_probability: float,
    average_win: float,
    average_loss: float,
    *,
    kelly_fraction: float = 0.25,
    max_capital_fraction: float = 0.05,
) -> FractionalKellyResult:
    """Return a capped fractional-Kelly bankroll allocation.

    ``average_win`` and ``average_loss`` are positive magnitudes measured on
    the same net-return basis (after fees and slippage). ``kelly_fraction``
    is the fraction of full Kelly to apply. The output is a fraction of total
    investable bankroll, before any separate portfolio/risk limits.
    """
    for name, value in (
        ("win_probability", win_probability),
        ("average_win", average_win),
        ("average_loss", average_loss),
        ("kelly_fraction", kelly_fraction),
        ("max_capital_fraction", max_capital_fraction),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if not 0.0 <= win_probability <= 1.0:
        raise ValueError("win_probability must be between 0 and 1")
    if average_win <= 0.0 or average_loss <= 0.0:
        raise ValueError("average_win and average_loss must be positive")
    if not 0.0 < kelly_fraction <= 1.0:
        raise ValueError("kelly_fraction must be in (0, 1]")
    if not 0.0 <= max_capital_fraction <= 1.0:
        raise ValueError("max_capital_fraction must be in [0, 1]")

    loss_probability = 1.0 - float(win_probability)
    payoff_ratio = float(average_win) / float(average_loss)
    full_kelly = float(win_probability) - loss_probability / payoff_ratio
    edge = float(win_probability) * float(average_win) - loss_probability * float(average_loss)
    warnings = []
    if full_kelly <= 0.0:
        warnings.append("non_positive_kelly_edge")
        recommended = 0.0
    else:
        recommended = min(float(max_capital_fraction), full_kelly * float(kelly_fraction))
    if win_probability in (0.0, 1.0):
        warnings.append("extreme_win_probability_requires_validation")

    return FractionalKellyResult(
        win_probability=float(win_probability),
        average_win=float(average_win),
        average_loss=float(average_loss),
        full_kelly_fraction=full_kelly,
        applied_fraction=float(kelly_fraction),
        recommended_capital_fraction=recommended,
        recommended_capital_pct=recommended * 100.0,
        expected_edge=edge,
        warnings=tuple(warnings),
    )
