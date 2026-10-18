from __future__ import annotations
from datetime import datetime

def weekday_candidate(moscow_time: datetime) -> bool:
    """Weekday is not proof that the exchange is open; holidays need authoritative data."""
    return moscow_time.weekday() < 5

def calendar_status(moscow_time: datetime) -> str:
    return "weekday_candidate" if weekday_candidate(moscow_time) else "weekend_candidate"
