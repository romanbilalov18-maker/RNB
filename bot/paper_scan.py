from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from bot.models import MarketQuote


@dataclass(frozen=True)
class PaperCandidate:
    instrument: Any
    quote: MarketQuote
    average_turnover: float


def rank_paper_candidates(
    instruments,
    quotes: Mapping[str, MarketQuote],
    *,
    held_tickers: set[str] | None = None,
    max_candidates: int = 10,
    max_quote_age_seconds: float = 120.0,
    minimum_candles: int = 20,
    now: datetime | None = None,
) -> list[PaperCandidate]:
    if max_candidates <= 0:
        raise ValueError("max_candidates must be positive")
    if max_quote_age_seconds <= 0:
        raise ValueError("max_quote_age_seconds must be positive")
    if minimum_candles <= 0:
        raise ValueError("minimum_candles must be positive")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    held_tickers = held_tickers or set()
    candidates = []

    for instrument in instruments:
        ticker = str(getattr(instrument, "ticker", "") or "")
        if not ticker:
            continue
        is_held = ticker in held_tickers or any(
            identifier in held_tickers
            for identifier in (
                str(getattr(instrument, "figi", "") or ""),
                str(getattr(instrument, "instrument_id", "") or ""),
            )
        )
        if str(getattr(instrument, "asset_type", "")).lower() != "share":
            continue
        if str(getattr(instrument, "currency", "")).upper() not in {"RUB", "RUR"}:
            continue
        if not bool(getattr(instrument, "tradable", False)):
            continue
        if not is_held and not bool(getattr(instrument, "buy_available", True)):
            continue

        quote = next(
            (
                quotes[key]
                for key in (
                    str(getattr(instrument, "figi", "") or ""),
                    str(getattr(instrument, "instrument_id", "") or ""),
                    ticker,
                )
                if key and key in quotes
            ),
            None,
        )
        if quote is None or quote.price <= 0 or len(quote.candles) < minimum_candles:
            continue
        quote_time = quote.timestamp
        if quote_time.tzinfo is None:
            quote_time = quote_time.replace(tzinfo=timezone.utc)
        age = (now - quote_time.astimezone(timezone.utc)).total_seconds()
        if age < -30 or age > max_quote_age_seconds:
            continue
        candles = quote.candles[-60:]
        if any(candle.close <= 0 or candle.volume < 0 for candle in candles):
            continue
        average_turnover = sum(
            candle.close * candle.volume for candle in candles
        ) / len(candles)
        if average_turnover <= 0:
            continue
        candidates.append(
            (is_held, PaperCandidate(instrument, quote, average_turnover))
        )

    candidates.sort(
        key=lambda pair: (
            0 if pair[0] else 1,
            -pair[1].average_turnover,
            pair[1].instrument.ticker,
        )
    )
    return [candidate for _, candidate in candidates[:max_candidates]]
