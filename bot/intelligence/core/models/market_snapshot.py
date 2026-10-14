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

    # Cross-sectional context computed from real T-Invest market data.
    market_return: Optional[float] = None
    market_breadth: Optional[float] = None
    market_sample_count: int = 0
    sector: Optional[str] = None
    sector_return: Optional[float] = None
    peer_return: Optional[float] = None
    peer_count: int = 0
    cross_asset_correlation: Optional[float] = None
    correlation_observations: int = 0
    historical_returns: tuple[float, ...] = ()
    market_return_history: tuple[float, ...] = ()
    sector_return_history: tuple[float, ...] = ()
    peer_return_history: tuple[float, ...] = ()
    historical_volume_ratios: tuple[float, ...] = ()

    def price_change(self) -> Optional[float]:
        if self.previous_price is None or self.previous_price == 0:
            return None
        return (self.price - self.previous_price) / self.previous_price
