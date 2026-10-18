from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class MarketContext:
    """Clock, broker-status and exchange-schedule facts for one scan cycle."""

    observed_at_utc: datetime
    observed_at_moscow: datetime
    weekday: str
    weekday_number: int
    weekday_candidate: bool
    calendar_status: str
    session: str
    session_phase: str
    broker_active_instruments: int
    broker_reported_instruments: int
    broker_status_verified: bool
    schedule_verified: bool = False
    exchange_sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    next_transition: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "observed_at_utc": self.observed_at_utc.isoformat(),
            "observed_at_moscow": self.observed_at_moscow.isoformat(),
            "weekday": self.weekday,
            "weekday_number": self.weekday_number,
            "weekday_candidate": self.weekday_candidate,
            "calendar_status": self.calendar_status,
            "session": self.session,
            "session_phase": self.session_phase,
            "broker_active_instruments": self.broker_active_instruments,
            "broker_reported_instruments": self.broker_reported_instruments,
            "broker_status_verified": self.broker_status_verified,
            "schedule_verified": self.schedule_verified,
            "exchange_sessions": self.exchange_sessions,
            "next_transition": self.next_transition,
        }
