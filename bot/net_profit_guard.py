"""Conservative net-profit gate for proposed entries.
Caller supplies real-data-derived expected return and observed spread; no market data is generated.
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

def assess_net_profit(*, expected_gross_return: float, commission_rate: float,
                      spread_pct: float, slippage_bps: float,
                      minimum_net_return: float = 0.0) -> NetProfitAssessment:
    """Rates are decimal fractions; spread_pct is full bid/ask spread."""
    values = {
        "expected_gross_return": expected_gross_return,
        "commission_rate": commission_rate,
        "spread_pct": spread_pct,
        "slippage_bps": slippage_bps,
        "minimum_net_return": minimum_net_return,
    }
    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be finite numeric")
    if expected_gross_return < 0:
        raise ValueError("expected_gross_return must be non-negative")
    if not 0 <= commission_rate <= 1:
        raise ValueError("commission_rate must be in [0, 1]")
    if not 0 <= spread_pct <= 1:
        raise ValueError("spread_pct must be in [0, 1]")
    if not 0 <= slippage_bps <= 10000:
        raise ValueError("slippage_bps must be in [0, 10000]")
    if not 0 <= minimum_net_return <= 1:
        raise ValueError("minimum_net_return must be in [0, 1]")
    commission = 2.0 * commission_rate
    spread_cost = spread_pct
    slippage_cost = 2.0 * slippage_bps / 10000.0
    net = expected_gross_return - commission - spread_cost - slippage_cost
    allowed = net >= minimum_net_return
    return NetProfitAssessment(allowed, float(expected_gross_return), commission,
        spread_cost, slippage_cost, net,
        "net_return_meets_threshold" if allowed else "net_return_below_threshold")
