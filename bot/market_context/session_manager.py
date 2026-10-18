from __future__ import annotations
from datetime import datetime
from .calendar import calendar_status, weekday_candidate
from .clock import current_times
from .models import MarketContext

_ACTIVE = {"NORMAL_TRADING", "OPENING_PERIOD", "CLOSING_PERIOD", "SECURITY_TRADING_STATUS_NORMAL_TRADING", "SECURITY_TRADING_STATUS_OPENING_PERIOD", "SECURITY_TRADING_STATUS_CLOSING_PERIOD"}

def build_market_context(now: datetime | None = None, trading_statuses: dict[str, str] | None = None, *, status_check_succeeded: bool = False) -> MarketContext:
    """Build conservative cycle context. Broker status is authoritative for eligibility."""
    utc, moscow = current_times(now)
    statuses = trading_statuses or {}
    active_count = sum(str(getattr(s, "name", s) or "").upper() in _ACTIVE for s in statuses.values())
    reported = len(statuses)
    # MOEX RUB shares do not trade on weekends. If broker status contradicts
    # the calendar, choose the conservative result and block trade eligibility.
    if not weekday_candidate(moscow):
        session, phase = "closed_by_weekend_calendar", "weekend_guard"
    elif not status_check_succeeded:
        session, phase = "unknown", "unverified"
    elif active_count == 0:
        session, phase = "closed_or_unavailable", "no_active_instruments"
    else:
        session, phase = "broker_reported_open", "active_status_confirmed"
    return MarketContext(utc, moscow, moscow.strftime("%A"), moscow.weekday(), weekday_candidate(moscow), calendar_status(moscow), session, phase, active_count, reported, status_check_succeeded, None)
