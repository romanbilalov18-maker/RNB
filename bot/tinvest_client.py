from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from bot.models import MarketQuote


class TInvestClient:
    """Read-only market-data client for the real T-Invest market."""

    def __init__(self, token: str):
        if not token or not token.strip():
            raise ValueError("T-Invest token is required")
        self.token = token.strip()

    def _client(self):
        try:
            from t_tech.invest import Client
        except ImportError as exc:
            raise RuntimeError(
                "t-tech-investments is not installed"
            ) from exc
        return Client(self.token)

    def last_prices(self, instrument_ids: list[str]) -> list[MarketQuote]:
        if not instrument_ids:
            return []

        with self._client() as client:
            response = client.market_data.get_last_prices(
                instrument_id=instrument_ids,
            )

        result = []
        for item in response.last_prices:
            result.append(
                MarketQuote(
                    ticker=str(getattr(item, "ticker", "") or ""),
                    price=_quotation_to_float(item.price),
                    timestamp=item.time,
                    volume=0,
                )
            )
        return result

    def candles(
        self,
        instrument_id: str,
        start: datetime,
        end: datetime,
        interval,
    ):
        if not instrument_id.strip():
            raise ValueError("instrument_id must not be empty")
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware")
        if start >= end:
            raise ValueError("start must be before end")

        with self._client() as client:
            return client.market_data.get_candles(
                instrument_id=instrument_id,
                from_=start.astimezone(timezone.utc),
                to=end.astimezone(timezone.utc),
                interval=interval,
            )

    def recent_candles(self, instrument_id: str, days: int = 30):
        if days <= 0:
            raise ValueError("days must be positive")

        try:
            from t_tech.invest import CandleInterval
        except ImportError as exc:
            raise RuntimeError(
                "t-tech-investments is not installed"
            ) from exc

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        return self.candles(
            instrument_id,
            start,
            end,
            CandleInterval.CANDLE_INTERVAL_1_DAY,
        )


def _quotation_to_float(value) -> float:
    units = getattr(value, "units", 0)
    nano = getattr(value, "nano", 0)
    return float(Decimal(str(units)) + Decimal(str(nano)) / Decimal("1000000000"))
