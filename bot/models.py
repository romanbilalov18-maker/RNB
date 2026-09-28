from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Signal = Literal["BUY", "SELL", "HOLD"]
Side = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class MarketQuote:
    ticker: str
    price: float
    timestamp: datetime
    closes: tuple[float, ...] = ()
    candles: tuple["HistoricalCandle", ...] = ()
    lot_size: int = 1


@dataclass(frozen=True)
class HistoricalCandle:
    ticker: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    def is_valid(self) -> bool:
        if not self.ticker.strip():
            return False
        if self.volume < 0:
            return False
        prices = (self.open, self.high, self.low, self.close)
        if any(price <= 0 for price in prices):
            return False
        return self.low <= self.open <= self.high and self.low <= self.close <= self.high


@dataclass(frozen=True)
class DecisionContext:
    ticker: str
    price: float
    timestamp: datetime
    candles: tuple[HistoricalCandle, ...]
    lot_size: int = 1

    @property
    def closes(self) -> tuple[float, ...]:
        return tuple(candle.close for candle in self.candles)

    @classmethod
    def from_quote(cls, quote: MarketQuote) -> "DecisionContext":
        if not quote.ticker.strip():
            raise ValueError("DecisionContext ticker must not be empty")

        lot_size = int(quote.lot_size or 1)
        if lot_size <= 0:
            raise ValueError("DecisionContext lot_size must be positive")

        if not quote.candles:
            if quote.closes:
                raise ValueError("DecisionContext requires historical candles")
            return cls(
                ticker=quote.ticker,
                price=quote.price,
                timestamp=quote.timestamp,
                candles=(),
                lot_size=lot_size,
            )

        candles = tuple(quote.candles)

        if any(candle.ticker != quote.ticker for candle in candles):
            raise ValueError("decision context candle ticker does not match quote ticker")

        derived_closes = tuple(candle.close for candle in candles)
        if quote.closes and tuple(quote.closes) != derived_closes:
            raise ValueError("quote closes do not match historical candle closes")

        return cls(
            ticker=quote.ticker,
            price=quote.price,
            timestamp=quote.timestamp,
            candles=candles,
            lot_size=lot_size,
        )


@dataclass(frozen=True)
class SignalResult:
    ticker: str
    signal: Signal
    confidence: float
    reason: str


@dataclass(frozen=True)
class OrderRequest:
    ticker: str
    side: Side
    quantity: int
    price: float
