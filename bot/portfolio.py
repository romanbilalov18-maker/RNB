from dataclasses import dataclass, field


@dataclass
class Position:
    quantity: int = 0
    average_price: float = 0.0


@dataclass
class Portfolio:
    cash: float
    commission_rate: float = 0.0005
    positions: dict[str, Position] = field(default_factory=dict)
    realized_pnl: float = 0.0
    commissions: float = 0.0

    def equity(self, prices: dict[str, float]) -> float:
        value = self.cash
        for ticker, position in self.positions.items():
            price = prices.get(ticker, position.average_price)
            value += position.quantity * price
        return value

    def execute(self, ticker: str, side: str, quantity: int, price: float) -> dict:
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if quantity <= 0 or price <= 0:
            raise ValueError("quantity and price must be positive")

        gross = quantity * price
        commission = gross * self.commission_rate

        position = self.positions.setdefault(ticker, Position())

        if side == "BUY":
            total_cost = gross + commission
            if total_cost > self.cash:
                raise ValueError("insufficient cash")

            old_value = position.quantity * position.average_price
            position.quantity += quantity
            position.average_price = (
                (old_value + gross) / position.quantity
                if position.quantity
                else 0.0
            )
            self.cash -= total_cost

        else:
            if quantity > position.quantity:
                raise ValueError("insufficient position")

            self.cash += gross - commission
            self.realized_pnl += quantity * (price - position.average_price) - commission
            position.quantity -= quantity
            if position.quantity == 0:
                position.average_price = 0.0

        self.commissions += commission

        if position.quantity == 0:
            self.positions.pop(ticker, None)

        return {
            "status": "FILLED",
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "price": price,
            "commission": commission,
            "cash": self.cash,
            "realized_pnl": self.realized_pnl,
        }
