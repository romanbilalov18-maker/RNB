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
    purchase_timestamp: datetime | None = None
    purchase_session: str | None = None
    purchase_exchange: str | None = None
    quote_unavailable_cycles: int = 0
    stagnant_sessions: int = 0
    last_health_status: str | None = None
    last_health_candle_timestamp: str | None = None


@dataclass(frozen=True)
class VirtualTrade:
    timestamp: datetime
    ticker: str
    side: str
    quantity: int
    price: float
    commission: float
    realized_pnl: float
    reason: str = "not recorded"
    entry_price: float | None = None
    # None means a legacy trade whose historical reserve transfer was not recorded.
    reserve_transfer: float | None = None
