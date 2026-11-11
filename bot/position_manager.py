from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math

from bot.stock_analysis import StockAnalysis
from bot.virtual_portfolio import VirtualPortfolio


@dataclass(frozen=True)
class PositionDecision:
    ticker: str
    action: str
    reason: str


def position_take_profit_price(position, commission_rate, fixed_take_profit, take_profit_r_multiple=None):
    """Return target price net of both entry and exit commission."""
    entry_cost = float(position.average_price) * (1.0 + commission_rate)
    if take_profit_r_multiple is None:
        return entry_cost * (1.0 + fixed_take_profit) / (1.0 - commission_rate)
    risk_per_share = getattr(position, "initial_stop_risk_per_share", None)
    if not (
        isinstance(risk_per_share, (int, float))
        and not isinstance(risk_per_share, bool)
        and math.isfinite(risk_per_share)
        and risk_per_share > 0
    ):
        initial_stop = getattr(position, "initial_stop_price", None)
        if (
            isinstance(initial_stop, (int, float))
            and not isinstance(initial_stop, bool)
            and math.isfinite(initial_stop)
            and 0 < initial_stop < float(position.average_price)
        ):
            risk_per_share = entry_cost - float(initial_stop) * (1.0 - commission_rate)
        else:
            return entry_cost * (1.0 + fixed_take_profit) / (1.0 - commission_rate)
    return (entry_cost + float(risk_per_share) * take_profit_r_multiple) / (1.0 - commission_rate)


class PositionManager:
    """Manage exits for existing virtual positions."""

    def __init__(
        self,
        stop_loss: float = -0.05,
        take_profit: float = 0.0015,
        negative_momentum: float = -0.02,
        take_profit_r_multiple: float | None = None,
    ):
        if not all(math.isfinite(value) for value in (stop_loss, take_profit, negative_momentum)):
            raise ValueError("exit thresholds must be finite")
        if take_profit_r_multiple is not None and (
            isinstance(take_profit_r_multiple, bool)
            or not isinstance(take_profit_r_multiple, (int, float))
            or not math.isfinite(take_profit_r_multiple)
            or take_profit_r_multiple <= 0
        ):
            raise ValueError("take_profit_r_multiple must be finite and positive")
        if stop_loss >= 0:
            raise ValueError("stop_loss must be negative")
        if take_profit < 0.0015:
            raise ValueError("take_profit must be at least 0.15%")
        if negative_momentum >= 0:
            raise ValueError("negative_momentum must be negative")
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.take_profit_r_multiple = float(take_profit_r_multiple) if take_profit_r_multiple is not None else None
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

            if (
                not isinstance(price, (int, float))
                or isinstance(price, bool)
                or not math.isfinite(price)
                or price <= 0
            ):
                decisions.append(
                    PositionDecision(ticker, "HOLD", "нет свежей или валидной цены")
                )
                continue

            entry_cost_per_share = position.average_price * (1.0 + portfolio.commission_rate)
            exit_proceeds_per_share = price * (1.0 - portfolio.commission_rate)
            net_return = exit_proceeds_per_share / entry_cost_per_share - 1.0

            # Take Profit and Stop Loss depend only on the actual market
            # price and must be checked before strategy analysis. A temporary
            # candle-analysis failure must never block a price-based exit.
            target_price = position_take_profit_price(
                position, portfolio.commission_rate, self.take_profit,
                self.take_profit_r_multiple,
            )
            if price >= target_price - 1e-12:
                label = (
                    f"{self.take_profit_r_multiple:g}R"
                    if self.take_profit_r_multiple is not None
                    else f"+{self.take_profit * 100:g}%"
                )
                decisions.append(PositionDecision(
                    ticker, "SELL", f"достигнут Take Profit {label}"
                ))
                continue

            # Persisted ATR/trailing stops are absolute market-price levels.
            # They are checked before the legacy percentage guard and do not
            # depend on strategy-analysis availability.
            persisted_stop = getattr(position, "stop_price", None)
            if (
                isinstance(persisted_stop, (int, float))
                and not isinstance(persisted_stop, bool)
                and math.isfinite(persisted_stop)
                and persisted_stop > 0
                and price <= persisted_stop + 1e-12
            ):
                decisions.append(
                    PositionDecision(
                        ticker,
                        "SELL",
                        f"сработал сохранённый защитный Stop Loss по цене {persisted_stop:.6f}",
                    )
                )
                continue

            # Use a tiny tolerance for the boundary comparison so that a
            # mathematically exact Stop Loss is not missed because of binary
            # floating-point rounding (e.g. -0.05 represented slightly above
            # or below its decimal value).
            if net_return <= self.stop_loss + 1e-12:
                decisions.append(
                    PositionDecision(ticker, "SELL", f"достигнут лимит убытка {self.stop_loss * 100:g}%")
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
        *,
        timestamp: datetime | None = None,
    ) -> list:
        trades = []
        timestamp = timestamp or datetime.now(timezone.utc)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")

        for decision in decisions:
            if decision.action != "SELL":
                continue

            position = portfolio.positions.get(decision.ticker)
            price = prices.get(decision.ticker)
            if (
                position is None
                or not isinstance(price, (int, float))
                or isinstance(price, bool)
                or not math.isfinite(price)
                or price <= 0
            ):
                continue

            trades.append(
                portfolio.sell(
                    ticker=decision.ticker,
                    quantity=position.quantity,
                    price=price,
                    timestamp=timestamp,
                    reason=decision.reason,
                )
            )

        return trades
