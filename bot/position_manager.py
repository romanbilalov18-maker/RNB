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
    """Manage exits for existing virtual positions."""

    def __init__(
        self,
        stop_loss: float = -0.05,
        take_profit: float = 0.0015,
        negative_momentum: float = -0.02,
    ):
        if stop_loss >= 0:
            raise ValueError("stop_loss must be negative")
        if take_profit < 0.0015:
            raise ValueError("take_profit must be at least 0.15%")
        if negative_momentum >= 0:
            raise ValueError("negative_momentum must be negative")
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.negative_momentum = negative_momentum

    def evaluate(
        self,
        portfolio: VirtualPortfolio,
        analyses: dict[str, StockAnalysis],
        prices: dict[str, float],
    ) -> list[PositionDecision]:
        decisions = []

        for ticker, position in portfolio.positions.items():
            price = prices.get(ticker)

            if price is None:
                decisions.append(PositionDecision(ticker, "HOLD", "нет свежей цены"))
                continue

            gross_return = price / position.average_price - 1.0
            net_return = gross_return - portfolio.commission_rate

            # Take Profit and Stop Loss depend only on the actual market
            # price and must be checked before strategy analysis. A temporary
            # candle-analysis failure must never block a price-based exit.
            if gross_return >= self.take_profit:
                decisions.append(
                    PositionDecision(
                        ticker,
                        "SELL",
                        f"достигнут Take Profit +{self.take_profit * 100:g}%",
                    )
                )
                continue

            # Use a tiny tolerance for the boundary comparison so that a
            # mathematically exact Stop Loss is not missed because of binary
            # floating-point rounding (e.g. -0.05 represented slightly above
            # or below its decimal value).
            if net_return <= self.stop_loss + 1e-12:
                decisions.append(
                    PositionDecision(ticker, "SELL", "достигнут лимит убытка -5%")
                )
                continue

            analysis = analyses.get(ticker)
            if analysis is None:
                decisions.append(PositionDecision(ticker, "HOLD", "нет свежего анализа"))
                continue

            if (
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
