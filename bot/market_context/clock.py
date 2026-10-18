from __future__ import annotations
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
MOSCOW = ZoneInfo("Europe/Moscow")

def current_times(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return an aware UTC/Moscow pair; naive injected times are rejected."""
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    utc = value.astimezone(timezone.utc)
    return utc, utc.astimezone(MOSCOW)
