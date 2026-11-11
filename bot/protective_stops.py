"""Volatility-aware protective-stop calculations from verified broker candles."""
from __future__ import annotations

import math

from bot.position_health import verified_completed_candles


def _number(value: object) -> float | None:
    if value is None:
        return None
    try:
        units = getattr(value, "units", None)
        nano = getattr(value, "nano", None)
        result = (
            float(units) + float(nano) / 1_000_000_000
            if units is not None and nano is not None
            else float(value)
        )
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def average_true_range(candles, period: int = 14) -> float | None:
    """Return simple ATR from the latest verified completed broker candles.

    Requires period + 1 completed candles so every true range has a prior
    close. Incomplete, duplicated, unordered, malformed or synthetic fallback
    observations are never manufactured here.
    """
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise ValueError("ATR period must be a positive integer")
    completed = verified_completed_candles(candles)
    if len(completed) < period + 1:
        return None
    sample = completed[-(period + 1):]
    ranges = []
    for previous, current in zip(sample, sample[1:]):
        high = _number(getattr(current, "high", None))
        low = _number(getattr(current, "low", None))
        previous_close = _number(getattr(previous, "close", None))
        if high is None or low is None or previous_close is None or high < low:
            return None
        ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    value = sum(ranges) / len(ranges)
    return value if math.isfinite(value) and value > 0 else None


def initial_atr_stop(entry_price: float, atr: float, multiplier: float = 2.0) -> float:
    """Place an initial long-position stop below entry by multiplier * ATR."""
    for name, value in (("entry_price", entry_price), ("atr", atr), ("multiplier", multiplier)):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"{name} must be finite and positive")
    stop = float(entry_price) - float(atr) * float(multiplier)
    if not math.isfinite(stop) or stop <= 0 or stop >= entry_price:
        raise ValueError("ATR stop is outside valid price range")
    return stop


def ratchet_trailing_stop(
    current_stop: float,
    high_watermark: float,
    atr: float,
    multiplier: float = 2.0,
) -> float:
    """Raise, but never lower, a long position's stop using ATR distance."""
    for name, value in (
        ("current_stop", current_stop),
        ("high_watermark", high_watermark),
        ("atr", atr),
        ("multiplier", multiplier),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"{name} must be finite and positive")
    return max(float(current_stop), float(high_watermark) - float(atr) * float(multiplier))
