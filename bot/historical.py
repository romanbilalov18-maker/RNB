from datetime import datetime, timedelta, timezone
from typing import Iterable

from bot.models import HistoricalCandle


class HistoricalDataProvider:
    """Read-only interface for historical OHLCV data."""

    def get_candles(
        self,
        ticker: str,
        start: datetime,
        end: datetime,
    ) -> list[HistoricalCandle]:
        raise NotImplementedError


class TBankHistoricalData(HistoricalDataProvider):
    """Read-only T-Bank historical candle adapter."""

    def __init__(self, token: str):
        if not token or not token.strip():
            raise ValueError("T-Bank token is required")
        self.token = token.strip()

    def get_candles(
        self,
        ticker: str,
        start: datetime,
        end: datetime,
    ) -> list[HistoricalCandle]:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware")
        if start >= end:
            raise ValueError("start must be before end")

        try:
            from t_tech.invest import CandleInterval, Client
        except ImportError as exc:
            raise RuntimeError(
                "T-Bank SDK is not installed; add t-tech-investments to requirements.txt"
            ) from exc

        with Client(self.token) as client:
            candles = client.get_all_candles(
                figi=ticker,
                from_=start.astimezone(timezone.utc),
                to=end.astimezone(timezone.utc),
                interval=CandleInterval.CANDLE_INTERVAL_1_MIN,
            )

            return [
                HistoricalCandle(
                    ticker=ticker,
                    timestamp=candle.time,
                    open=_quotation_to_float(candle.open),
                    high=_quotation_to_float(candle.high),
                    low=_quotation_to_float(candle.low),
                    close=_quotation_to_float(candle.close),
                    volume=int(candle.volume),
                )
                for candle in candles
            ]


def recent_window(days: int = 1) -> tuple[datetime, datetime]:
    if days <= 0:
        raise ValueError("days must be positive")
    end = datetime.now(timezone.utc)
    return end - timedelta(days=days), end


def normalize_candles(
    candles: Iterable[HistoricalCandle],
) -> list[HistoricalCandle]:
    """Return valid candles sorted chronologically with duplicate timestamps removed."""
    ordered = sorted(candles, key=lambda candle: candle.timestamp)
    result: list[HistoricalCandle] = []
    seen: set[datetime] = set()

    for candle in ordered:
        if candle.timestamp in seen:
            continue
        if candle.is_valid():
            result.append(candle)
            seen.add(candle.timestamp)

    return result


def _quotation_to_float(value) -> float:
    units = getattr(value, "units", None)
    nano = getattr(value, "nano", None)

    if units is None and nano is None:
        return float(value)

    return float(units or 0) + float(nano or 0) / 1_000_000_000
