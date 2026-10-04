from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MarketSnapshot:
    """Universal market snapshot for intelligence analysis."""

    symbol: str
    price: float
    previous_price: Optional[float] = None
    volume: Optional[float] = None
    average_volume: Optional[float] = None
    volatility: Optional[float] = None
    momentum: Optional[float] = None
    liquidity: Optional[float] = None

    # Latest real candle data when the source provides OHLCV.
    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    close_price: Optional[float] = None
    candle_volume: Optional[float] = None
    average_candle_volume: Optional[float] = None
    candle_range: Optional[float] = None
    close_position: Optional[float] = None
    volume_ratio: Optional[float] = None
    lot_size: Optional[int] = None

    def price_change(self) -> Optional[float]:
        if self.previous_price is None or self.previous_price == 0:
            return None
        return (self.price - self.previous_price) / self.previous_price
