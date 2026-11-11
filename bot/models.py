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
    health_condition: str | None = None
    health_condition_since: str | None = None
    # Persisted protective-stop state. None denotes a legacy position whose
    # stop must be initialized from verified market data before adaptive logic.
    initial_stop_price: float | None = None
    stop_price: float | None = None
    high_watermark: float | None = None
    initial_stop_risk_per_share: float | None = None
    stop_model: str | None = None
    stop_updated_at: datetime | None = None


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
