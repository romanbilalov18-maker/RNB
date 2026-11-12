"""Shadow-mode gross expectancy estimates from completed virtual exits.

Only completed SELL events supplied by the caller are used. The estimator is
diagnostic: it does not create signals, approve entries, or submit orders.
Historical commissions are reversed from realized P&L so the result remains
gross; the existing NetProfitGuard can then apply current round-trip costs once.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


@dataclass(frozen=True)
class ExpectedValueEstimate:
    available: bool
    sample_count: int
    wins: int
    losses: int
    win_probability: float | None
    average_win_return: float | None
    average_loss_return: float | None
    expected_gross_return: float | None
    excluded_count: int
    reason: str


def calculate_expected_value(
    win_probability: float,
    average_win_return: float,
    average_loss_return: float,
) -> float:
    """Return gross expectancy as a fraction of entry notional.

    average_loss_return is a positive loss magnitude. Transaction costs must
    either be included in both payoff estimates or applied separately later;
    this function deliberately does not estimate or deduct costs.
    """
    values = {
        "win_probability": win_probability,
        "average_win_return": average_win_return,
        "average_loss_return": average_loss_return,
    }
    for name, value in values.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{name} must be a finite number")

    if not 0.0 <= win_probability <= 1.0:
        raise ValueError("win_probability must be in [0, 1]")
    if average_win_return < 0.0 or average_loss_return < 0.0:
        raise ValueError("average win and loss returns must be non-negative")

    return (
        float(win_probability) * float(average_win_return)
        - (1.0 - float(win_probability)) * float(average_loss_return)
    )


def estimate_expected_value(
    trades: Iterable[object],
    *,
    commission_rate: float,
    minimum_samples: int = 20,
) -> ExpectedValueEstimate:
    """Estimate gross expectancy from prior completed virtual SELL events.

    Each SELL event is one observation, matching VirtualPortfolio's existing
    per-exit expectancy convention (partial exits are separate observations).
    Win/loss classification uses reconstructed gross P&L. Entry commission is
    reconstructed using the supplied, historically applicable commission rate;
    exit commission comes from the persisted VirtualTrade. Current spread and
    slippage are intentionally left to NetProfitGuard.

    The caller must provide only exits known before the decision timestamp.
    Insufficient history or a missing win/loss class returns unavailable.
    """
    if (
        isinstance(commission_rate, bool)
        or not isinstance(commission_rate, (int, float))
        or not math.isfinite(commission_rate)
        or not 0.0 <= commission_rate < 1.0
    ):
        raise ValueError("commission_rate must be finite and in [0, 1)")
    if (
        isinstance(minimum_samples, bool)
        or not isinstance(minimum_samples, int)
        or minimum_samples < 1
    ):
        raise ValueError("minimum_samples must be a positive integer")

    win_returns: list[float] = []
    loss_returns: list[float] = []
    excluded = 0

    for trade in trades:
        if getattr(trade, "side", None) != "SELL":
            continue

        quantity = getattr(trade, "quantity", None)
        entry_price = getattr(trade, "entry_price", None)
        realized_pnl = getattr(trade, "realized_pnl", None)
        exit_commission = getattr(trade, "commission", None)

        numeric_values = (entry_price, realized_pnl, exit_commission)
        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity <= 0
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in numeric_values
            )
            or entry_price <= 0
            or exit_commission < 0
        ):
            excluded += 1
            continue

        entry_notional = quantity * float(entry_price)
        gross_pnl = (
            float(realized_pnl)
            + float(exit_commission)
            + entry_notional * float(commission_rate)
        )
        gross_return = gross_pnl / entry_notional
        if not math.isfinite(gross_return):
            excluded += 1
            continue

        if gross_return > 0.0:
            win_returns.append(gross_return)
        else:
            loss_returns.append(-gross_return)

    wins = len(win_returns)
    losses = len(loss_returns)
    sample_count = wins + losses

    if sample_count < minimum_samples:
        return ExpectedValueEstimate(
            False, sample_count, wins, losses, None, None, None, None,
            excluded, "insufficient_history",
        )
    if not wins or not losses:
        return ExpectedValueEstimate(
            False, sample_count, wins, losses, None, None, None, None,
            excluded, "both_win_and_loss_outcomes_required",
        )

    probability = wins / sample_count
    average_win = sum(win_returns) / wins
    average_loss = sum(loss_returns) / losses
    expected = calculate_expected_value(probability, average_win, average_loss)

    return ExpectedValueEstimate(
        True,
        sample_count,
        wins,
        losses,
        probability,
        average_win,
        average_loss,
        expected,
        excluded,
        "shadow_estimate_ready",
    )
