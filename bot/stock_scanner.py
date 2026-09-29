from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from bot.models import MarketQuote


@dataclass(frozen=True)
class StockCandidate:
    instrument_id: str
    ticker: str
    name: str
    price: float
    volume: int
    score: float


class StockScanner:
    """Build a shortlist of liquid RUB shares from current market data."""

    def __init__(self, max_candidates: int = 10):
        if max_candidates <= 0:
            raise ValueError("max_candidates must be positive")
        self.max_candidates = max_candidates

    def scan(self, instruments: Iterable[object], quotes: Iterable[MarketQuote]) -> list[StockCandidate]:
        quote_by_ticker = {
            quote.ticker: quote
            for quote in quotes
            if quote.ticker and quote.price > 0
        }

        candidates: list[StockCandidate] = []

        for instrument in instruments:
            ticker = str(getattr(instrument, "ticker", "") or "").strip()
            instrument_id = str(
                getattr(instrument, "uid", "")
                or getattr(instrument, "instrument_id", "")
                or ""
            ).strip()

            if not ticker or not instrument_id:
                continue

            if not self._is_share(instrument):
                continue

            if not self._is_rub(instrument):
                continue

            if not self._is_tradable(instrument):
                continue

            quote = quote_by_ticker.get(ticker)
            if quote is None:
                continue

            score = self._score(instrument, quote)
            candidates.append(
                StockCandidate(
                    instrument_id=instrument_id,
                    ticker=ticker,
                    name=str(getattr(instrument, "name", "") or ticker),
                    price=quote.price,
                    volume=quote.volume,
                    score=score,
                )
            )

        candidates.sort(
            key=lambda item: (-item.score, -item.volume, item.ticker)
        )
        return candidates[: self.max_candidates]

    @staticmethod
    def _is_share(instrument: object) -> bool:
        instrument_type = str(
            getattr(instrument, "instrument_type", "")
            or getattr(instrument, "asset_type", "")
            or ""
        ).lower()

        class_code = str(getattr(instrument, "class_code", "") or "").upper()

        return (
            "share" in instrument_type
            or "stock" in instrument_type
            or class_code in {"TQBR", "TQPI", "TQIF"}
        )

    @staticmethod
    def _is_rub(instrument: object) -> bool:
        currency = str(
            getattr(instrument, "currency", "")
            or getattr(instrument, "currency_code", "")
            or ""
        ).upper()
        return currency in {"RUB", "RUR"}

    @staticmethod
    def _is_tradable(instrument: object) -> bool:
        buy = getattr(instrument, "buy_available_flag", None)
        sell = getattr(instrument, "sell_available_flag", None)
        if buy is False or sell is False:
            return False

        status = str(
            getattr(instrument, "trading_status", "")
            or ""
        ).lower()

        if status and any(value in status for value in ("not", "closed", "halt")):
            return False

        return True

    @staticmethod
    def _score(instrument: object, quote: MarketQuote) -> float:
        """Score current liquidity without making a trading decision."""
        lot = int(getattr(instrument, "lot", 1) or 1)
        if lot <= 0:
            lot = 1

        turnover = quote.price * max(quote.volume, 0) * lot
        if turnover <= 0:
            return 0.0

        # Logarithmic scaling keeps very large volumes from dominating completely.
        import math

        return math.log10(turnover + 1.0)


def quote_is_fresh(
    quote: MarketQuote,
    max_age_seconds: float = 120.0,
    now: datetime | None = None,
) -> bool:
    if max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be positive")

    now = now or datetime.now(timezone.utc)
    timestamp = quote.timestamp
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    age = (now - timestamp.astimezone(timezone.utc)).total_seconds()
    return -30 <= age <= max_age_seconds
