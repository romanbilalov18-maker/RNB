from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import re
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


_BASE_URL = "https://invest-public-api.tbank.ru/rest/"
_INSTRUMENTS_SERVICE = "tinkoff.public.invest.api.contract.v1.InstrumentsService"
_MARKET_DATA_SERVICE = "tinkoff.public.invest.api.contract.v1.MarketDataService"
_BATCH_SIZE = 100


class TInvestClient:
    """Small read-only HTTP client for the official T-Invest REST API."""

    def __init__(
        self,
        token: str,
        *,
        base_url: str = _BASE_URL,
        timeout: float = 15.0,
    ):
        if not token or not token.strip():
            raise ValueError("T-Invest token is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.token = token.strip()
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout

    def __enter__(self) -> "TInvestClient":
        return self

    def __exit__(self, *_args) -> None:
        return None

    def shares(self) -> list[SimpleNamespace]:
        response = self._post(
            _INSTRUMENTS_SERVICE,
            "Shares",
            {"instrumentStatus": "INSTRUMENT_STATUS_BASE"},
        )
        return response.instruments

    def last_prices(self, instrument_ids: list[str]) -> list[SimpleNamespace]:
        result = []
        for batch in _chunks(instrument_ids):
            response = self._post(
                _MARKET_DATA_SERVICE,
                "GetLastPrices",
                {"instrumentId": batch},
            )
            result.extend(response.last_prices)
        return result

    def close_prices(self, instrument_ids: list[str]) -> list[SimpleNamespace]:
        result = []
        for batch in _chunks(instrument_ids):
            response = self._post(
                _MARKET_DATA_SERVICE,
                "GetClosePrices",
                {"instruments": [{"instrumentId": value} for value in batch]},
            )
            result.extend(response.close_prices)
        return result

    def candles(
        self,
        instrument_id: str,
        start: datetime,
        end: datetime,
        interval: str = "CANDLE_INTERVAL_DAY",
    ) -> list[SimpleNamespace]:
        if not instrument_id.strip():
            raise ValueError("instrument_id must not be empty")
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware")
        if start >= end:
            raise ValueError("start must be before end")
        response = self._post(
            _MARKET_DATA_SERVICE,
            "GetCandles",
            {
                "instrumentId": instrument_id,
                "from": _format_timestamp(start),
                "to": _format_timestamp(end),
                "interval": interval,
            },
        )
        return response.candles

    def recent_candles(
        self,
        instrument_id: str,
        days: int = 30,
    ) -> list[SimpleNamespace]:
        if days <= 0:
            raise ValueError("days must be positive")
        end = datetime.now(timezone.utc)
        return self.candles(instrument_id, end - timedelta(days=days), end)

    def _post(self, service: str, method: str, payload: dict) -> SimpleNamespace:
        url = f"{self.base_url}{service}/{method}"
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "RNB-TInvest-REST/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = response.read()
        except HTTPError as exc:
            detail = _error_detail(exc.read())
            detail = detail.replace(self.token, "[redacted]")
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"T-Invest API returned HTTP {exc.code}{suffix}") from None
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise RuntimeError(
                f"Could not connect to T-Invest API ({type(reason).__name__})"
            ) from None

        try:
            decoded = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RuntimeError("T-Invest API returned invalid JSON") from None
        if not isinstance(decoded, dict):
            raise RuntimeError("T-Invest API returned an unexpected response")
        if "error" in decoded or "code" in decoded and "message" in decoded:
            detail = _error_detail(data).replace(self.token, "[redacted]")
            raise RuntimeError(f"T-Invest API error{': ' + detail if detail else ''}")
        return _namespace(decoded)


def _chunks(values: list[str], size: int = _BATCH_SIZE):
    for offset in range(0, len(values), size):
        yield values[offset:offset + size]


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _namespace(value):
    if isinstance(value, list):
        return [_namespace(item) for item in value]
    if isinstance(value, dict):
        if set(value) == {"units", "nano"}:
            return float(
                Decimal(str(value["units"]))
                + Decimal(str(value["nano"])) / Decimal("1000000000")
            )
        return SimpleNamespace(**{
            _snake_case(key): _namespace(item)
            for key, item in value.items()
        })
    if isinstance(value, str):
        if "T" in value and (value.endswith("Z") or "+" in value[10:]):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass
    return value


def _snake_case(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _error_detail(data: bytes) -> str:
    try:
        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    detail = payload.get("message") or payload.get("details")
    if isinstance(detail, str):
        return detail[:300]
    return ""
