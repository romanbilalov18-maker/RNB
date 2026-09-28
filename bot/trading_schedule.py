from dataclasses import dataclass
from datetime import datetime, time
from typing import Callable
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class TradingWindow:
    start: time
    end: time
    min_confidence: float


class TradingSchedule:
    """Confidence windows plus optional real-time instrument availability."""

    def __init__(self, timezone_name: str = "Europe/Moscow", windows: tuple[TradingWindow, ...] = (
        TradingWindow(time(9, 50), time(11, 0), 0.40),
        TradingWindow(time(11, 0), time(19, 0), 0.50),
        TradingWindow(time(19, 0), time(23, 50), 0.40),
    ), market_open_checker: Callable[[str], bool] | None = None) -> None:
        if not windows:
            raise ValueError("at least one trading window is required")
        self.timezone = ZoneInfo(timezone_name)
        self.windows = windows
        self.market_open_checker = market_open_checker
        for window in windows:
            if not 0 <= window.min_confidence <= 1:
                raise ValueError("window min_confidence must be between 0 and 1")
            if window.start >= window.end:
                raise ValueError("window start must be before window end")

    @classmethod
    def from_string(cls, raw: str, timezone_name: str = "Europe/Moscow", market_open_checker: Callable[[str], bool] | None = None) -> "TradingSchedule":
        windows = []
        for item in raw.split(","):
            item = item.strip()
            if not item:
                continue
            try:
                interval, threshold = item.split("=", 1)
                start_text, end_text = interval.split("-", 1)
                windows.append(TradingWindow(time.fromisoformat(start_text), time.fromisoformat(end_text), float(threshold)))
            except ValueError as exc:
                raise ValueError("TRADING_WINDOWS must look like '09:50-11:00=0.40,11:00-19:00=0.50,19:00-23:50=0.40'") from exc
        return cls(timezone_name, tuple(windows), market_open_checker)

    @classmethod
    def from_env(cls, market_open_checker: Callable[[str], bool] | None = None) -> "TradingSchedule":
        import os
        return cls.from_string(
            os.getenv("TRADING_WINDOWS", "09:50-11:00=0.40,11:00-19:00=0.50,19:00-23:50=0.40").strip(),
            os.getenv("TRADING_TIMEZONE", "Europe/Moscow").strip(),
            market_open_checker,
        )

    def for_timestamp(self, timestamp: datetime) -> TradingWindow | None:
        local = timestamp.astimezone(self.timezone)
        current = local.time().replace(tzinfo=None)
        for window in self.windows:
            if window.start <= current < window.end:
                return window
        return None

    def is_open(self, timestamp: datetime, instrument: str | None = None) -> bool:
        if self.market_open_checker is not None and instrument is not None:
            return bool(self.market_open_checker(instrument))
        return self.for_timestamp(timestamp) is not None

    def min_confidence(self, timestamp: datetime, fallback: float) -> float:
        window = self.for_timestamp(timestamp)
        return window.min_confidence if window is not None else fallback
