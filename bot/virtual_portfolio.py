from dataclasses import dataclass, field
import math

from bot.models import VirtualPosition, VirtualTrade


@dataclass(frozen=True)
class PositionPerformance:
    ticker: str
    quantity: int
    average_price: float
    market_price: float
    invested_value: float
    current_value: float
    unrealized_pnl: float
    unrealized_return_pct: float
    estimated_sell_commission: float
    net_if_sold_now: float
    net_return_pct_if_sold_now: float


@dataclass(frozen=True)
class PortfolioStatistics:
    total_trades: int
    buy_trades: int
    sell_trades: int
    profitable_trades: int
    losing_trades: int
    win_rate_pct: float
    best_realized_trade: float
    worst_realized_trade: float
    average_profitable_trade: float
    average_losing_trade: float
    total_realized_pnl: float
    total_commissions: float
    current_equity: float
    total_pnl: float
    total_return_pct: float
    peak_equity: float
    max_drawdown: float
    max_drawdown_pct: float


@dataclass
class VirtualPortfolio:
    """Persistent virtual portfolio used for paper trading."""

    initial_balance: float
    commission_rate: float = 0.0005
    cash: float | None = None
    positions: dict[str, VirtualPosition] = field(default_factory=dict)
    trades: list[VirtualTrade] = field(default_factory=list)
    realized_pnl: float = 0.0
    commissions: float = 0.0
    protected_cash: float = 0.0
    profit_reserve_rate: float = 0.7

    def __post_init__(self) -> None:
        for name, value in (
            ("initial_balance", self.initial_balance),
            ("commission_rate", self.commission_rate),
            ("profit_reserve_rate", self.profit_reserve_rate),
            ("protected_cash", self.protected_cash),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{name} must be a finite number")
        if self.initial_balance <= 0:
            raise ValueError("initial_balance must be positive")
        if self.commission_rate < 0:
            raise ValueError("commission_rate must not be negative")
        if not 0.0 <= self.profit_reserve_rate <= 1.0:
            raise ValueError("profit_reserve_rate must be between 0 and 1")
        if self.protected_cash < 0:
            raise ValueError("protected_cash must be non-negative")
        if self.cash is None:
            self.cash = self.initial_balance

        # State loaded from SQLite is just as untrusted as constructor input.
        # Reject corrupt/non-finite account values before they can authorize buys.
        for name, value in (
            ("cash", self.cash),
            ("realized_pnl", self.realized_pnl),
            ("commissions", self.commissions),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{name} must be a finite number")
        if self.cash < 0:
            raise ValueError("cash must be non-negative")
        if self.commissions < 0:
            raise ValueError("commissions must be non-negative")

    def buy(
        self, ticker: str, quantity: int, price: float, timestamp,
        reason: str = "BUY accepted by PositionSizer",
    ) -> VirtualTrade:
        self._validate_order(ticker, quantity, price)
        gross = quantity * price
        commission = gross * self.commission_rate
        total = gross + commission
        if total > self.cash:
            raise ValueError("insufficient virtual cash")
        position = self.positions.get(ticker)
        if position is None:
            position = VirtualPosition(ticker, 0, 0.0)
            self.positions[ticker] = position
        old_value = position.quantity * position.average_price
        position.quantity += quantity
        position.average_price = (old_value + gross) / position.quantity
        self.cash -= total
        self.commissions += commission
        trade = VirtualTrade(
            timestamp, ticker, "BUY", quantity, price, commission, 0.0,
            reason=reason, entry_price=price,
        )
        self.trades.append(trade)
        return trade

    def sell(
        self, ticker: str, quantity: int, price: float, timestamp,
        reason: str = "not recorded",
    ) -> VirtualTrade:
        self._validate_order(ticker, quantity, price)
        position = self.positions.get(ticker)
        if position is None or quantity > position.quantity:
            raise ValueError("insufficient virtual position")
        gross = quantity * price
        commission = gross * self.commission_rate
        entry_commission = quantity * position.average_price * self.commission_rate
        realized_pnl = quantity * (price - position.average_price) - commission - entry_commission
        # Move a fixed share of net realized profit into a protected reserve.
        # It is removed from spendable cash immediately and never included in
        # the cash available to PositionSizer.
        reserve_transfer = max(realized_pnl, 0.0) * self.profit_reserve_rate
        self.cash += gross - commission - reserve_transfer
        self.protected_cash += reserve_transfer
        self.realized_pnl += realized_pnl
        self.commissions += commission
        position.quantity -= quantity
        if position.quantity == 0:
            del self.positions[ticker]
        trade = VirtualTrade(
            timestamp, ticker, "SELL", quantity, price, commission, realized_pnl,
            reason=reason, entry_price=position.average_price,
        )
        self.trades.append(trade)
        return trade

    def equity(self, market_prices: dict[str, float]) -> float:
        """Return complete mark-to-market equity; fail closed on missing/invalid quotes."""
        value, missing = self.equity_with_available_prices(market_prices)
        if missing:
            raise ValueError(f"missing or invalid market price for {', '.join(missing)}")
        return value

    def equity_with_available_prices(
        self, market_prices: dict[str, float]
    ) -> tuple[float, tuple[str, ...]]:
        """Return cash plus positions with valid quotes and list unvalued positions.

        The partial value is diagnostic/conservative only; it must never be
        presented as complete equity or used to authorize trades at stale prices.
        """
        value = float(self.cash) + float(self.protected_cash)
        missing = []
        for ticker, position in self.positions.items():
            price = market_prices.get(ticker)
            if (
                not isinstance(price, (int, float))
                or isinstance(price, bool)
                or not math.isfinite(price)
                or price <= 0
            ):
                missing.append(ticker)
                continue
            value += position.quantity * float(price)
        return value, tuple(sorted(missing))

    def position_performance(self, market_prices: dict[str, float]) -> list[PositionPerformance]:
        """Return mark-to-market performance for every open position."""
        result = []

        for ticker, position in self.positions.items():
            market_price = market_prices.get(ticker)
            if (
                not isinstance(market_price, (int, float))
                or isinstance(market_price, bool)
                or not math.isfinite(market_price)
                or market_price <= 0
            ):
                # Unpriced holdings are reported separately by the caller; never
                # invent a mark-to-market value for them.
                continue

            invested = position.quantity * position.average_price
            current = position.quantity * market_price
            unrealized = current - invested
            sell_commission = current * self.commission_rate
            entry_commission = invested * self.commission_rate
            net_if_sold = unrealized - sell_commission - entry_commission

            result.append(
                PositionPerformance(
                    ticker=ticker,
                    quantity=position.quantity,
                    average_price=position.average_price,
                    market_price=market_price,
                    invested_value=invested,
                    current_value=current,
                    unrealized_pnl=unrealized,
                    unrealized_return_pct=unrealized / invested * 100.0,
                    estimated_sell_commission=sell_commission,
                    net_if_sold_now=net_if_sold,
                    net_return_pct_if_sold_now=net_if_sold / invested * 100.0,
                )
            )

        return result

    def statistics(
        self,
        current_equity: float,
        equity_history: list[float] | None = None,
    ) -> PortfolioStatistics:
        """Return cumulative trading and equity statistics."""
        sells = [trade for trade in self.trades if trade.side == "SELL"]
        buys = [trade for trade in self.trades if trade.side == "BUY"]
        profitable = [trade for trade in sells if trade.realized_pnl > 0]
        losing = [trade for trade in sells if trade.realized_pnl < 0]

        history = list(equity_history or [])
        if not history:
            history = [self.initial_balance]
        if not history or history[-1] != current_equity:
            history.append(current_equity)

        peak = history[0]
        max_drawdown = 0.0
        max_drawdown_pct = 0.0
        for value in history:
            peak = max(peak, value)
            drawdown = peak - value
            drawdown_pct = drawdown / peak * 100.0 if peak else 0.0
            max_drawdown = max(max_drawdown, drawdown)
            max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)

        total_pnl = current_equity - self.initial_balance

        return PortfolioStatistics(
            total_trades=len(self.trades),
            buy_trades=len(buys),
            sell_trades=len(sells),
            profitable_trades=len(profitable),
            losing_trades=len(losing),
            win_rate_pct=(len(profitable) / len(sells) * 100.0) if sells else 0.0,
            best_realized_trade=max((trade.realized_pnl for trade in sells), default=0.0),
            worst_realized_trade=min((trade.realized_pnl for trade in sells), default=0.0),
            average_profitable_trade=(
                sum(trade.realized_pnl for trade in profitable) / len(profitable)
                if profitable
                else 0.0
            ),
            average_losing_trade=(
                sum(trade.realized_pnl for trade in losing) / len(losing)
                if losing
                else 0.0
            ),
            total_realized_pnl=self.realized_pnl,
            total_commissions=self.commissions,
            current_equity=current_equity,
            total_pnl=total_pnl,
            total_return_pct=total_pnl / self.initial_balance * 100.0,
            peak_equity=peak,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
        )

    def _validate_order(self, ticker: str, quantity: int, price: float) -> None:
        if not isinstance(ticker, str) or not ticker.strip():
            raise ValueError("ticker must not be empty")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        if (
            not isinstance(price, (int, float))
            or isinstance(price, bool)
            or not math.isfinite(price)
            or price <= 0
        ):
            raise ValueError("price must be a finite positive number")
