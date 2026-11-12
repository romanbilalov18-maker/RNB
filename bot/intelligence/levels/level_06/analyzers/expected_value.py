"""Shadow-mode gross expectancy from completed virtual trade episodes.

Partial exits belonging to one holding lifecycle are aggregated. Only trades
with persisted actual entry commissions and an explicit closed-episode allowlist
are eligible. No current commission rate is used to reconstruct historical fees.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
    """Return gross expectancy as a fraction of entry notional."""
    values = {
        "win_probability": win_probability,
        "average_win_return": average_win_return,
        "average_loss_return": average_loss_return,
    }
    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")
    if not 0.0 <= win_probability <= 1.0:
        raise ValueError("win_probability must be in [0, 1]")
    if average_win_return < 0.0 or average_loss_return < 0.0:
        raise ValueError("average win and loss returns must be non-negative")
    return float(win_probability) * float(average_win_return) - (
        1.0 - float(win_probability)
    ) * float(average_loss_return)


def estimate_expected_value(
    trades: Iterable[object],
    *,
    closed_episode_ids: set[str] | None = None,
    as_of: datetime | None = None,
    minimum_samples: int = 20,
) -> ExpectedValueEstimate:
    """Estimate gross expectancy from completed episodes only.

    Each episode is one observation regardless of the number of partial exits.
    The caller must pass IDs known to be fully closed at the decision time and
    an aware as_of timestamp. Events at or after as_of are excluded to prevent
    look-ahead leakage. Historical entry commissions are taken from each persisted exit allocation;
    exit commissions are taken from the exit itself. Legacy rows lacking this
    metadata are excluded rather than reverse-engineered with today's rate.
    """
    if closed_episode_ids is None or not isinstance(closed_episode_ids, set):
        raise ValueError("closed_episode_ids must be an explicit set")
    if (
        not isinstance(as_of, datetime)
        or as_of.tzinfo is None
        or as_of.utcoffset() is None
    ):
        raise ValueError("as_of must be a timezone-aware datetime")
    if any(not isinstance(item, str) or not item for item in closed_episode_ids):
        raise ValueError("closed_episode_ids must contain non-empty strings")
    if isinstance(minimum_samples, bool) or not isinstance(minimum_samples, int) or minimum_samples < 1:
        raise ValueError("minimum_samples must be a positive integer")

    episodes: dict[str, dict[str, float]] = {}
    excluded = 0
    for trade in trades:
        if getattr(trade, "side", None) != "SELL":
            continue
        episode_id = getattr(trade, "trade_episode_id", None)
        quantity = getattr(trade, "quantity", None)
        entry_price = getattr(trade, "entry_price", None)
        realized_pnl = getattr(trade, "realized_pnl", None)
        exit_commission = getattr(trade, "commission", None)
        entry_commission = getattr(trade, "entry_commission", None)
        timestamp = getattr(trade, "timestamp", None)
        values = (entry_price, realized_pnl, exit_commission, entry_commission)
        if (
            not isinstance(episode_id, str) or not episode_id
            or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values)
            or entry_price <= 0 or exit_commission < 0 or entry_commission < 0
            or not isinstance(timestamp, datetime)
            or timestamp.tzinfo is None or timestamp.utcoffset() is None
        ):
            excluded += 1
            continue
        if timestamp >= as_of:
            excluded += 1
            continue
        if episode_id not in closed_episode_ids:
            continue
        bucket = episodes.setdefault(episode_id, {"gross_pnl": 0.0, "entry_notional": 0.0})
        bucket["gross_pnl"] += float(realized_pnl) + float(exit_commission) + float(entry_commission)
        bucket["entry_notional"] += quantity * float(entry_price)

    returns = []
    for bucket in episodes.values():
        if bucket["entry_notional"] <= 0 or not math.isfinite(bucket["gross_pnl"]):
            excluded += 1
            continue
        value = bucket["gross_pnl"] / bucket["entry_notional"]
        if math.isfinite(value) and value != 0.0:
            returns.append(value)
        else:
            excluded += 1

    wins = [value for value in returns if value > 0]
    losses = [-value for value in returns if value < 0]
    sample_count = len(returns)
    if sample_count < minimum_samples:
        reason = "insufficient_history"
    elif not wins or not losses:
        reason = "both_win_and_loss_outcomes_required"
    else:
        reason = "shadow_estimate_ready"

    if reason != "shadow_estimate_ready":
        return ExpectedValueEstimate(
            False, sample_count, len(wins), len(losses), None, None, None, None,
            excluded, reason,
        )

    probability = len(wins) / sample_count
    average_win = sum(wins) / len(wins)
    average_loss = sum(losses) / len(losses)
    return ExpectedValueEstimate(
        True, sample_count, len(wins), len(losses), probability,
        average_win, average_loss,
        calculate_expected_value(probability, average_win, average_loss),
        excluded, reason,
    )
