from dataclasses import dataclass, field

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

    def __post_init__(self) -> None:
        if self.initial_balance <= 0:
            raise ValueError("initial_balance must be positive")
        if self.commission_rate < 0:
            raise ValueError("commission_rate must not be negative")
        if self.cash is None:
            self.cash = self.initial_balance

    def buy(self, ticker: str, quantity: int, price: float, timestamp) -> VirtualTrade:
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
        trade = VirtualTrade(timestamp, ticker, "BUY", quantity, price, commission, 0.0)
        self.trades.append(trade)
        return trade

    def sell(self, ticker: str, quantity: int, price: float, timestamp) -> VirtualTrade:
        self._validate_order(ticker, quantity, price)
        position = self.positions.get(ticker)
        if position is None or quantity > position.quantity:
            raise ValueError("insufficient virtual position")
        gross = quantity * price
        commission = gross * self.commission_rate
        realized_pnl = quantity * (price - position.average_price) - commission
        self.cash += gross - commission
        self.realized_pnl += realized_pnl
        self.commissions += commission
        position.quantity -= quantity
        if position.quantity == 0:
            del self.positions[ticker]
        trade = VirtualTrade(timestamp, ticker, "SELL", quantity, price, commission, realized_pnl)
        self.trades.append(trade)
        return trade

    def equity(self, market_prices: dict[str, float]) -> float:
        value = self.cash
        for ticker, position in self.positions.items():
            price = market_prices.get(ticker)
            if price is None:
                raise ValueError(f"missing market price for {ticker}")
            value += position.quantity * price
        return value

    def position_performance(self, market_prices: dict[str, float]) -> list[PositionPerformance]:
        """Return mark-to-market performance for every open position."""
        result = []

        for ticker, position in self.positions.items():
            market_price = market_prices.get(ticker)
            if market_price is None:
                raise ValueError(f"missing market price for {ticker}")

            invested = position.quantity * position.average_price
            current = position.quantity * market_price
            unrealized = current - invested
            sell_commission = current * self.commission_rate
            net_if_sold = unrealized - sell_commission

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

    def _validate_order(self, ticker: str, quantity: int, price: float) -> None:
        if not ticker.strip():
            raise ValueError("ticker must not be empty")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if price <= 0:
            raise ValueError("price must be positive")
