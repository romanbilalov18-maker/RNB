"""Health checks for open virtual-portfolio positions.

This module reports prolonged price stagnation separately from missing/stale
quotes. It never turns a flat price by itself into an automatic sell signal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone


FLAT_MOVE_TOLERANCE_PCT = 0.001  # 0.1% close-to-close
FLAT_REVIEW_SESSIONS = 5
LOW_RANGE_REVIEW_SESSIONS = 10
LOW_RANGE_THRESHOLD_PCT = 0.005  # 0.5% high-low close range


@dataclass(frozen=True)
class PositionHealth:
    ticker: str
    status: str
    recommendation: str
    candles_checked: int
    flat_sessions: int
    recent_range_pct: float | None
    current_price_available: bool


def _price(value: object) -> float | None:
    if value is None:
        return None
    try:
        units = getattr(value, "units", None)
        nano = getattr(value, "nano", None)
        if units is not None and nano is not None:
            number = float(units) + float(nano) / 1_000_000_000
        else:
            number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def verified_completed_candles(
    candles: list[object] | tuple[object, ...] | None,
) -> list[object]:
    """Return unique, valid, explicitly completed broker candles in time order."""
    by_timestamp: dict[datetime, object] = {}
    for candle in candles or ():
        if getattr(candle, "is_complete", None) is not True:
            continue
        candle_time = getattr(candle, "time", None)
        if (
            not isinstance(candle_time, datetime)
            or candle_time.tzinfo is None
            or candle_time.utcoffset() is None
            or _price(getattr(candle, "close", None)) is None
        ):
            continue
        timestamp = candle_time.astimezone(timezone.utc)
        # Preserve the first source record for a duplicated timestamp.
        if timestamp not in by_timestamp:
            by_timestamp[timestamp] = candle
    return [candle for _, candle in sorted(by_timestamp.items())]


def assess_position_health(
    ticker: str,
    candles: list[object] | tuple[object, ...] | None,
    *,
    current_price_available: bool,
    momentum: float | None = None,
    trend_strength: float | None = None,
    market_closed: bool = False,
) -> PositionHealth:
    """Flag stagnant holdings and quote gaps without treating either as a sell."""
    completed_candles = verified_completed_candles(candles)
    completed = [
        _price(getattr(candle, "close", None))
        for candle in completed_candles
    ]
    completed = [price for price in completed if price is not None]

    # A flat session is a flat close-to-close transition. One candle alone
    # cannot establish stagnation because there is no prior session to compare.
    flat_sessions = 0
    for newer, older in zip(reversed(completed), reversed(completed[:-1])):
        if abs(newer / older - 1.0) <= FLAT_MOVE_TOLERANCE_PCT:
            flat_sessions += 1
        else:
            break

    recent = completed[-LOW_RANGE_REVIEW_SESSIONS:]
    recent_range_pct = (
        (max(recent) - min(recent)) / min(recent)
        if len(recent) >= LOW_RANGE_REVIEW_SESSIONS and min(recent) > 0
        else None
    )

    if market_closed:
        status = "MARKET_CLOSED"
        recommendation = "WAIT_FOR_NEXT_EXCHANGE_SESSION; a scheduled closure is not a quote failure"
    elif not current_price_available:
        status = "QUOTE_UNAVAILABLE"
        recommendation = "VERIFY_MARKET_DATA; do not infer a sell from a missing quote"
    elif flat_sessions >= FLAT_REVIEW_SESSIONS or (
        recent_range_pct is not None and recent_range_pct <= LOW_RANGE_THRESHOLD_PCT
    ):
        bearish = (
            momentum is not None
            and trend_strength is not None
            and momentum <= -0.02
            and trend_strength < 0
        )
        status = "PROLONGED_STAGNATION"
        recommendation = (
            "EXIT_REVIEW_WITH_EXISTING_RISK_RULES"
            if bearish
            else "HOLD_AND_REVIEW_LIQUIDITY_TREND_AND_INSTRUMENT_STATUS"
        )
    else:
        status = "NORMAL_MONITORING"
        recommendation = "CONTINUE_NORMAL_POSITION_RULES"

    return PositionHealth(
        ticker=ticker,
        status=status,
        recommendation=recommendation,
        candles_checked=len(completed),
        flat_sessions=flat_sessions,
        recent_range_pct=recent_range_pct,
        current_price_available=current_price_available,
    )
