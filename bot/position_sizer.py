from __future__ import annotations

from dataclasses import dataclass
from itertools import product


@dataclass(frozen=True)
class PositionPlan:
    ticker: str
    price: float
    lot_size: int
    lots: int
    quantity: int
    gross_value: float
    commission: float
    total_cost: float
    target_weight: float
    actual_weight: float


class PositionSizer:
    """Size virtual positions using volatility, lot size, commission and cash."""

    def __init__(
        self,
        commission_rate: float,
        max_position_weight: float = 0.70,
    ):
        if commission_rate < 0:
            raise ValueError("commission_rate must not be negative")
        if not 0 < max_position_weight <= 1:
            raise ValueError("max_position_weight must be in (0, 1]")

        self.commission_rate = commission_rate
        self.max_position_weight = max_position_weight

    def plan(self, cash: float, analyses, prices, lot_sizes) -> list[PositionPlan]:
        if cash <= 0:
            raise ValueError("cash must be positive")
        if not analyses:
            return []

        targets = self._target_weights(analyses)
        unit_costs = {
            analysis.ticker: prices[analysis.ticker]
            * lot_sizes[analysis.ticker]
            * (1.0 + self.commission_rate)
            for analysis in analyses
        }

        max_lots = {
            ticker: int(cash / cost)
            for ticker, cost in unit_costs.items()
        }

        tickers = [analysis.ticker for analysis in analyses]
        best = None

        ranges = [
            range(max_lots[ticker] + 1)
            for ticker in tickers
        ]

        for lot_counts in product(*ranges):
            invested = sum(
                lots * unit_costs[ticker]
                for ticker, lots in zip(tickers, lot_counts)
            )
            if invested <= 0 or invested > cash + 1e-9:
                continue

            weights = {
                ticker: (
                    lots * unit_costs[ticker] / invested
                    if invested > 0
                    else 0.0
                )
                for ticker, lots in zip(tickers, lot_counts)
            }

            if any(
                weight > self.max_position_weight + 1e-9
                for weight in weights.values()
            ):
                continue

            deviation = sum(
                (weights[ticker] - targets[ticker]) ** 2
                for ticker in tickers
            )

            utilization = invested / cash
            objective = utilization - 0.50 * deviation

            candidate = (objective, invested, lot_counts, weights)
            if best is None or candidate[:2] > best[:2]:
                best = candidate

        if best is None:
            return []

        _, invested, lot_counts, weights = best
        plans = []

        for analysis, lots in zip(analyses, lot_counts):
            if lots <= 0:
                continue

            ticker = analysis.ticker
            price = prices[ticker]
            lot_size = lot_sizes[ticker]
            quantity = lots * lot_size
            gross = quantity * price
            commission = gross * self.commission_rate

            plans.append(
                PositionPlan(
                    ticker=ticker,
                    price=price,
                    lot_size=lot_size,
                    lots=lots,
                    quantity=quantity,
                    gross_value=gross,
                    commission=commission,
                    total_cost=gross + commission,
                    target_weight=targets[ticker],
                    actual_weight=weights[ticker],
                )
            )

        return plans

    @staticmethod
    def _target_weights(analyses) -> dict[str, float]:
        inverse_risk = {}
        for analysis in analyses:
            volatility = max(float(analysis.volatility), 1e-9)
            inverse_risk[analysis.ticker] = 1.0 / volatility

        total = sum(inverse_risk.values())
        return {
            ticker: value / total
            for ticker, value in inverse_risk.items()
        }
