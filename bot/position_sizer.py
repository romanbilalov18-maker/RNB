from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import math


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
    """Size new virtual positions against the whole portfolio.

    Small search spaces use the original exhaustive optimizer. Large spaces
    use a bounded deterministic greedy/local-search optimizer to avoid the
    Cartesian-product explosion. The heuristic preserves the same feasibility
    checks and objective, but may choose a different allocation for large
    cases; small cases remain exact and are used as regression references.
    """

    EXACT_SEARCH_LIMIT = 100_000

    def __init__(
        self,
        commission_rate: float,
        max_position_weight: float = 0.35,
    ):
        if not math.isfinite(commission_rate):
            raise ValueError("commission_rate must be finite")
        if not math.isfinite(max_position_weight):
            raise ValueError("max_position_weight must be finite")
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

        ranges = [range(max_lots[ticker] + 1) for ticker in tickers]
        combinations = math.prod(len(values) for values in ranges)

        if combinations <= self.EXACT_SEARCH_LIMIT:
            best = self._exhaustive_best(
                tickers, ranges, unit_costs, existing_values, targets,
                cash, total_equity,
            )
        else:
            best = self._heuristic_best(
                tickers, max_lots, unit_costs, existing_values, targets,
                cash, total_equity,
            )

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

    def _evaluate(
        self, lot_counts, tickers, unit_costs, existing_values, targets,
        cash, total_equity,
    ):
        invested = sum(
            lots * unit_costs[ticker]
            for ticker, lots in zip(tickers, lot_counts)
        )
        if invested <= 0 or invested > cash + 1e-9:
            return None

        weights = {
            ticker: (
                existing_values.get(ticker, 0.0) + lots * unit_costs[ticker]
            ) / total_equity
            for ticker, lots in zip(tickers, lot_counts)
        }
        if any(
            weight > self.max_position_weight + 1e-9
            for weight in weights.values()
        ):
            return None

        deviation = sum(
            (
                lots * unit_costs[ticker] / invested - targets[ticker]
            ) ** 2
            for ticker, lots in zip(tickers, lot_counts)
        )
        objective = invested / cash - 0.50 * deviation
        return objective, invested, tuple(lot_counts), weights

    def _exhaustive_best(
        self, tickers, ranges, unit_costs, existing_values, targets,
        cash, total_equity,
    ):
        best = None
        for lot_counts in product(*ranges):
            candidate = self._evaluate(
                lot_counts, tickers, unit_costs, existing_values, targets,
                cash, total_equity,
            )
            if candidate is not None and (
                best is None or candidate[:2] > best[:2]
            ):
                best = candidate
        return best

    def _heuristic_best(
        self, tickers, max_lots, unit_costs, existing_values, targets,
        cash, total_equity,
    ):
        counts = [0] * len(tickers)
        best = None

        # Greedily add feasible lots, choosing the best resulting objective.
        # Every accepted state respects cash and concentration constraints.
        while True:
            next_best = None
            for index, ticker in enumerate(tickers):
                if counts[index] >= max_lots[ticker]:
                    continue
                trial = counts.copy()
                trial[index] += 1
                candidate = self._evaluate(
                    trial, tickers, unit_costs, existing_values, targets,
                    cash, total_equity,
                )
                if candidate is not None and (
                    next_best is None or candidate[:2] > next_best[:2]
                ):
                    next_best = candidate
            if next_best is None:
                break
            counts = list(next_best[2])
            best = next_best

        if best is None:
            return None

        # Improve the greedy allocation through one-lot transfers. The finite
        # state space and strict objective improvement prevent cycling.
        while True:
            improved = best
            current = list(best[2])
            for source, source_ticker in enumerate(tickers):
                if current[source] <= 0:
                    continue
                for destination, destination_ticker in enumerate(tickers):
                    if source == destination or current[destination] >= max_lots[destination_ticker]:
                        continue
                    trial = current.copy()
                    trial[source] -= 1
                    trial[destination] += 1
                    candidate = self._evaluate(
                        trial, tickers, unit_costs, existing_values, targets,
                        cash, total_equity,
                    )
                    if candidate is not None and candidate[:2] > improved[:2]:
                        improved = candidate
            if improved[:2] <= best[:2]:
                break
            best = improved
        return best

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
