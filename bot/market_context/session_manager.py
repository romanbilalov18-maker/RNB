from __future__ import annotations

from datetime import datetime
from typing import Mapping

from .calendar import calendar_status, weekday_candidate
from .clock import current_times
from .models import MarketContext


_ACTIVE = {
    "NORMAL_TRADING", "OPENING_PERIOD", "CLOSING_PERIOD",
    "SECURITY_TRADING_STATUS_NORMAL_TRADING",
    "SECURITY_TRADING_STATUS_OPENING_PERIOD",
    "SECURITY_TRADING_STATUS_CLOSING_PERIOD",
    "SESSION_OPEN", "SECURITY_TRADING_STATUS_SESSION_OPEN",
    "DEALER_NORMAL_TRADING", "SECURITY_TRADING_STATUS_DEALER_NORMAL_TRADING",
}


def build_market_context(
    now: datetime | None = None,
    trading_statuses: dict[str, str] | None = None,
    *,
    status_check_succeeded: bool = False,
    exchange_sessions: Mapping[str, object] | None = None,
    schedule_check_succeeded: bool = False,
) -> MarketContext:
    """Build cycle context; exchange schedules, not weekdays, define sessions."""
    utc, moscow = current_times(now)
    statuses = trading_statuses or {}
    sessions = dict(exchange_sessions or {})
    active_count = sum(
        str(getattr(status, "name", status) or "").upper() in _ACTIVE
        for status in statuses.values()
    )
    reported = len(statuses)

    verified_sessions = [
        item for item in sessions.values() if bool(getattr(item, "verified", False))
    ]
    open_sessions = [
        item for item in verified_sessions if bool(getattr(item, "is_open", False))
    ]
    schedule_verified = bool(schedule_check_succeeded and verified_sessions)

    if not schedule_check_succeeded:
        session, phase = "unknown", "schedule_unavailable"
    elif open_sessions:
        session = "scheduled_open"
        phases = sorted({str(getattr(item, "phase", "unknown")) for item in open_sessions})
        phase = phases[0] if len(phases) == 1 else "multiple_sessions"
    elif sessions and len(verified_sessions) == len(sessions):
        session, phase = "closed_by_exchange_schedule", "no_open_interval"
    else:
        session, phase = "unknown", "schedule_incomplete"

    future_transitions = [
        transition
        for item in verified_sessions
        if isinstance((transition := getattr(item, "next_transition", None)), datetime)
        and transition > utc
    ]
    next_transition = min(future_transitions).isoformat() if future_transitions else None

    serialized_sessions = {
        key: (item.to_dict() if callable(getattr(item, "to_dict", None)) else {})
        for key, item in sessions.items()
    }
    return MarketContext(
        observed_at_utc=utc,
        observed_at_moscow=moscow,
        weekday=moscow.strftime("%A"),
        weekday_number=moscow.weekday(),
        weekday_candidate=weekday_candidate(moscow),
        calendar_status=calendar_status(moscow),
        session=session,
        session_phase=phase,
        broker_active_instruments=active_count,
        broker_reported_instruments=reported,
        broker_status_verified=status_check_succeeded and reported > 0,
        schedule_verified=schedule_verified,
        exchange_sessions=serialized_sessions,
        next_transition=next_transition,
    )
