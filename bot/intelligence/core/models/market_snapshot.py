from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    price: float
    previous_price: Optional[float] = None
    volume: Optional[float] = None
    average_volume: Optional[float] = None
    volatility: Optional[float] = None
    momentum: Optional[float] = None
    liquidity: Optional[float] = None

    def price_change(self) -> Optional[float]:
        if self.previous_price is None or self.previous_price == 0:
            return None
        return (self.price - self.previous_price) / self.previous_price
