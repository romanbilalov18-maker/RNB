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
    """Size new virtual positions against the whole portfolio."""

    def __init__(
        self,
        commission_rate: float,
        max_position_weight: float = 0.35,
    ):
        if commission_rate < 0:
            raise ValueError("commission_rate must not be negative")
        if not 0 < max_position_weight <= 1:
            raise ValueError("max_position_weight must be in (0, 1]")

        self.commission_rate = commission_rate
        self.max_position_weight = max_position_weight

    def plan(
        self,
        cash: float,
        analyses,
        prices,
        lot_sizes,
        existing_positions=None,
        existing_values=None,
        total_equity: float | None = None,
    ) -> list[PositionPlan]:
        if cash <= 0:
            raise ValueError("cash must be positive")
        if not analyses:
            return []

        existing_values = {
            str(ticker): max(float(value), 0.0)
            for ticker, value in (existing_values or {}).items()
        }
        existing_positions = set(existing_positions or existing_values)
        if total_equity is None:
            total_equity = cash + sum(existing_values.values())
        if total_equity <= 0:
            raise ValueError("total_equity must be positive")

        targets = self._target_weights(analyses)
        tickers = [analysis.ticker for analysis in analyses]
        unit_costs = {
            analysis.ticker: prices[analysis.ticker]
            * lot_sizes[analysis.ticker]
            * (1.0 + self.commission_rate)
            for analysis in analyses
        }

        max_lots = {}
        for ticker in tickers:
            if ticker in existing_positions:
                max_lots[ticker] = 0
                continue
            capacity = (
                self.max_position_weight * total_equity
                - existing_values.get(ticker, 0.0)
            )
            max_lots[ticker] = max(0, int(capacity / unit_costs[ticker]))

        best = None
        ranges = [range(max_lots[ticker] + 1) for ticker in tickers]

        for lot_counts in product(*ranges):
            invested = sum(
                lots * unit_costs[ticker]
                for ticker, lots in zip(tickers, lot_counts)
            )
            if invested <= 0 or invested > cash + 1e-9:
                continue

            portfolio_value = total_equity + invested
            weights = {
                ticker: (
                    existing_values.get(ticker, 0.0)
                    + lots * unit_costs[ticker]
                ) / portfolio_value
                for ticker, lots in zip(tickers, lot_counts)
            }

            if any(
                weight > self.max_position_weight + 1e-9
                for weight in weights.values()
            ):
                continue

            new_value_weights = {
                ticker: lots * unit_costs[ticker] / invested
                if invested > 0 else 0.0
                for ticker, lots in zip(tickers, lot_counts)
            }
            deviation = sum(
                (new_value_weights[ticker] - targets[ticker]) ** 2
                for ticker in tickers
            )
            utilization = invested / cash
            objective = utilization - 0.50 * deviation
            candidate = (objective, invested, lot_counts, weights)

            if best is None or candidate[:2] > best[:2]:
                best = candidate

        if best is None:
            return []

        _, _, lot_counts, weights = best
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
