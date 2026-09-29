from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MarketQuote:
    ticker: str
    price: float
    timestamp: datetime
    volume: int = 0


@dataclass
class VirtualPosition:
    ticker: str
    quantity: int
    average_price: float


@dataclass(frozen=True)
class VirtualTrade:
    timestamp: datetime
    ticker: str
    side: str
    quantity: int
    price: float
    commission: float
    realized_pnl: float
