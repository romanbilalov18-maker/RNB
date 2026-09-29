from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from bot.stock_analysis import StockAnalysis
from bot.virtual_portfolio import VirtualPortfolio


@dataclass(frozen=True)
class PositionDecision:
    ticker: str
    action: str
    reason: str


class PositionManager:
    """Decide whether an existing virtual position should be held or sold."""

    def __init__(
        self,
        stop_loss: float = -0.05,
        negative_momentum: float = -0.02,
    ):
        if stop_loss >= 0:
            raise ValueError("stop_loss must be negative")
        if negative_momentum >= 0:
            raise ValueError("negative_momentum must be negative")
        self.stop_loss = stop_loss
        self.negative_momentum = negative_momentum

    def evaluate(
        self,
        portfolio: VirtualPortfolio,
        analyses: dict[str, StockAnalysis],
        prices: dict[str, float],
    ) -> list[PositionDecision]:
        decisions = []

        for ticker, position in portfolio.positions.items():
            analysis = analyses.get(ticker)
            price = prices.get(ticker)

            if analysis is None or price is None:
                decisions.append(
                    PositionDecision(ticker, "HOLD", "нет свежего анализа")
                )
                continue

            net_return = (
                price / position.average_price
                - 1.0
                - portfolio.commission_rate
            )

            if net_return <= self.stop_loss:
                decisions.append(
                    PositionDecision(ticker, "SELL", "достигнут лимит убытка")
                )
            elif (
                analysis.momentum <= self.negative_momentum
                and analysis.trend_strength < 0
            ):
                decisions.append(
                    PositionDecision(
                        ticker,
                        "SELL",
                        "моментум и тренд стали отрицательными",
                    )
                )
            else:
                decisions.append(
                    PositionDecision(ticker, "HOLD", "сигнал продажи отсутствует")
                )

        return decisions

    def execute_sales(
        self,
        portfolio: VirtualPortfolio,
        decisions: list[PositionDecision],
        prices: dict[str, float],
    ) -> list:
        trades = []
        timestamp = datetime.now(timezone.utc)

        for decision in decisions:
            if decision.action != "SELL":
                continue

            position = portfolio.positions.get(decision.ticker)
            price = prices.get(decision.ticker)
            if position is None or price is None:
                continue

            trades.append(
                portfolio.sell(
                    ticker=decision.ticker,
                    quantity=position.quantity,
                    price=price,
                    timestamp=timestamp,
                )
            )

        return trades
