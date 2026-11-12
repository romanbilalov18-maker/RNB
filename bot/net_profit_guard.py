"""Conservative net-profit gate for proposed entries.

Caller supplies a real-data-derived gross price return and observed full
bid/ask spread. Returns are fractions of entry notional. The exit commission
is scaled by the expected exit notional, avoiding a small systematic
underestimate on profitable trades.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class NetProfitAssessment:
    allowed: bool
    expected_gross_return: float
    round_trip_commission: float
    spread_cost: float
    slippage_cost: float
    expected_net_return: float
    reason: str


def assess_net_profit(
    *,
    expected_gross_return: float,
    commission_rate: float,
    spread_pct: float,
    slippage_bps: float,
    minimum_net_return: float = 0.0,
) -> NetProfitAssessment:
    """Assess expected net return as a fraction of entry notional.

    expected_gross_return is the price return before trading costs.
    commission_rate applies independently to entry and exit notionals.
    spread_pct is the full quoted bid/ask spread as a fraction.
    slippage_bps is the assumed slippage on each side of the round trip.
    All percentage inputs are decimal fractions, except slippage in bps.
    """
    values = {
        "expected_gross_return": expected_gross_return,
        "commission_rate": commission_rate,
        "spread_pct": spread_pct,
        "slippage_bps": slippage_bps,
        "minimum_net_return": minimum_net_return,
    }
    for name, value in values.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{name} must be finite numeric")

    if expected_gross_return < 0:
        raise ValueError("expected_gross_return must be non-negative")
    if not 0 <= commission_rate < 1:
        raise ValueError("commission_rate must be in [0, 1)")
    if not 0 <= spread_pct <= 1:
        raise ValueError("spread_pct must be in [0, 1]")
    if not 0 <= slippage_bps <= 10000:
        raise ValueError("slippage_bps must be in [0, 10000]")
    if not 0 <= minimum_net_return <= 1:
        raise ValueError("minimum_net_return must be in [0, 1]")

    # Entry commission is r of entry notional. Exit commission is r of
    # expected exit notional: (1 + gross return) times entry notional.
    commission = commission_rate * (2.0 + expected_gross_return)
    spread_cost = float(spread_pct)
    slippage_cost = 2.0 * slippage_bps / 10000.0
    net = expected_gross_return - commission - spread_cost - slippage_cost

    if not all(math.isfinite(value) for value in (commission, net)):
        raise ValueError("calculated transaction costs or net return are not finite")

    allowed = net >= minimum_net_return
    return NetProfitAssessment(
        allowed=allowed,
        expected_gross_return=float(expected_gross_return),
        round_trip_commission=commission,
        spread_cost=spread_cost,
        slippage_cost=slippage_cost,
        expected_net_return=net,
        reason=(
            "net_return_meets_threshold"
            if allowed
            else "net_return_below_threshold"
        ),
    )
