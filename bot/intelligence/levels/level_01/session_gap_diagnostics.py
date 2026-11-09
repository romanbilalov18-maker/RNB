"""Compare observed candle dates with dates supplied by an official exchange calendar.

This module intentionally does not infer weekends, holidays, or exchange sessions.
The caller must supply the trading dates from a verified broker/exchange schedule.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable
from zoneinfo import ZoneInfo

MOSCOW = ZoneInfo("Europe/Moscow")


def trading_session_date(value: str | date | datetime) -> date:
    """Normalize a date/timestamp to its Moscow trading-session date.

    Date-only values remain unchanged. Naive timestamps are treated as UTC,
    matching the historical CSV ingestion contract; aware timestamps are
    converted to Europe/Moscow before extracting the session date.
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        return value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("calendar date must not be empty")
        try:
            parsed_date = date.fromisoformat(text)
            return parsed_date
        except ValueError:
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(f"invalid ISO calendar date/timestamp: {value!r}") from exc
    else:
        raise TypeError("calendar values must be ISO strings, dates, or datetimes")

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(MOSCOW).date()


def find_missing_trading_dates(
    official_trading_dates: Iterable[str | date | datetime],
    observed_candle_timestamps: Iterable[str | date | datetime],
) -> list[str]:
    """Return official trading dates with no observed candle.

    The official calendar is authoritative: weekends and exchange holidays are
    naturally excluded when absent from ``official_trading_dates``. No market
    prices or candle rows are fabricated by this diagnostic.
    """
    expected = {trading_session_date(value) for value in official_trading_dates}
    observed = {trading_session_date(value) for value in observed_candle_timestamps}
    return [day.isoformat() for day in sorted(expected - observed)]
