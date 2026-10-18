from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from .clock import MOSCOW


TRADABLE_PHASES = frozenset({
    "dealer",
    "premarket",
    "opening_auction",
    "morning",
    "main",
    "closing_auction",
    "evening_opening_auction",
    "evening",
    "scheduled_trading",
})


@dataclass(frozen=True)
class ExchangeSession:
    exchange: str
    verified: bool
    schedule_date: str | None
    is_trading_day: bool | None
    session: str
    phase: str
    is_open: bool
    next_transition: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "verified": self.verified,
            "schedule_date": self.schedule_date,
            "is_trading_day": self.is_trading_day,
            "session": self.session,
            "phase": self.phase,
            "is_open": self.is_open,
            "next_transition": (
                self.next_transition.isoformat()
                if self.next_transition is not None else None
            ),
        }


def normalize_exchange(value: object) -> str:
    return str(value or "").strip().upper()


def _utc_datetime(value: object) -> datetime | None:
    if not isinstance(value, datetime) or value.year < 2000:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _schedule_date(value: object) -> date | None:
    if isinstance(value, datetime):
        normalized = _utc_datetime(value)
        return normalized.astimezone(MOSCOW).date() if normalized else None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            normalized = _utc_datetime(parsed)
            if normalized:
                return normalized.astimezone(MOSCOW).date()
        except ValueError:
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
    return None


def _inside(now: datetime, start: object, end: object) -> bool:
    start_utc, end_utc = _utc_datetime(start), _utc_datetime(end)
    return start_utc is not None and end_utc is not None and start_utc <= now < end_utc


def _interval_windows(day: object) -> list[tuple[str, datetime, datetime]]:
    result = []
    for item in getattr(day, "intervals", ()) or ():
        span = getattr(item, "interval", None)
        start = _utc_datetime(
            getattr(span, "start_ts", None) or getattr(span, "start_time", None)
        )
        end = _utc_datetime(
            getattr(span, "end_ts", None) or getattr(span, "end_time", None)
        )
        interval_type = str(getattr(item, "type", "") or "").strip().lower()
        if start is not None and end is not None and start < end:
            result.append((interval_type, start, end))
    return result


def _interval_phase(interval_type: str) -> str | None:
    name = interval_type.replace("-", "_").replace(" ", "_")
    if "clearing" in name:
        return "clearing"
    if "dealer" in name and "trading" in name:
        return "dealer"
    if "opening_auction" in name:
        return "opening_auction"
    if "closing_auction" in name:
        return "closing_auction"
    if "premarket" in name or "pre_market" in name:
        return "premarket"
    if "morning" in name:
        return "morning"
    if "evening" in name and "auction" in name:
        return "evening_opening_auction"
    if "evening" in name and "trading" in name:
        return "evening"
    if "regular_trading_session" in name or "trading_session" in name:
        return "main"
    return None


def _future_transitions(day: object, now: datetime, intervals: list[tuple[str, datetime, datetime]]) -> datetime | None:
    candidates = []
    for name in (
        "clearing_start_time", "clearing_end_time",
        "premarket_start_time", "premarket_end_time",
        "opening_auction_start_time", "opening_auction_end_time",
        "closing_auction_start_time", "closing_auction_end_time",
        "evening_opening_auction_start_time",
        "evening_start_time", "evening_end_time",
        "start_time", "end_time",
    ):
        value = _utc_datetime(getattr(day, name, None))
        if value is not None and value > now:
            candidates.append(value)
    for _, start, end in intervals:
        if start > now:
            candidates.append(start)
        if end > now:
            candidates.append(end)
    return min(candidates) if candidates else None


def _field_phase(day: object, now: datetime) -> str | None:
    # Clearing takes priority over broad start/end windows.
    if _inside(now, getattr(day, "clearing_start_time", None), getattr(day, "clearing_end_time", None)):
        return "clearing"
    if _inside(now, getattr(day, "opening_auction_start_time", None), getattr(day, "opening_auction_end_time", None)):
        return "opening_auction"
    if _inside(now, getattr(day, "closing_auction_start_time", None), getattr(day, "closing_auction_end_time", None)):
        return "closing_auction"
    evening_auction_start = getattr(day, "evening_opening_auction_start_time", None)
    evening_start = getattr(day, "evening_start_time", None)
    if _inside(now, evening_auction_start, evening_start):
        return "evening_opening_auction"
    if _inside(now, getattr(day, "premarket_start_time", None), getattr(day, "premarket_end_time", None)):
        return "premarket"
    if _inside(now, evening_start, getattr(day, "evening_end_time", None)):
        return "evening"
    if _inside(now, getattr(day, "start_time", None), getattr(day, "end_time", None)):
        return "main"
    return None


def resolve_exchange_session(
    exchange: str,
    schedule: object | None,
    now: datetime,
) -> ExchangeSession:
    """Resolve the current session from the broker's official schedule.

    Unknown/missing schedules never grant trade eligibility. An explicit active
    interval can override a non-trading calendar date (e.g. supported dealer
    sessions), but a weekday alone cannot.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    now_utc = now.astimezone(timezone.utc)
    exchange_name = str(getattr(schedule, "exchange", exchange) or exchange)
    if schedule is None:
        return ExchangeSession(exchange_name, False, None, None, "unknown", "schedule_missing", False)

    target_date = now_utc.astimezone(MOSCOW).date()
    days = getattr(schedule, "days", ()) or ()
    day = next((candidate for candidate in days if _schedule_date(getattr(candidate, "date", None)) == target_date), None)
    if day is None:
        return ExchangeSession(exchange_name, False, None, None, "unknown", "current_day_not_returned", False)

    intervals = _interval_windows(day)
    next_transition = _future_transitions(day, now_utc, intervals)
    date_text = target_date.isoformat()
    is_trading_day = bool(getattr(day, "is_trading_day", False))

    active_intervals = [
        (kind, phase, start, end)
        for kind, start, end in intervals
        if start <= now_utc < end
        for phase in [_interval_phase(kind)]
        if phase is not None
    ]

    # The dealer interval is explicit evidence of an internal market session.
    dealer_active = next((item for item in active_intervals if item[1] == "dealer"), None)
    if dealer_active is not None:
        return ExchangeSession(exchange_name, True, date_text, is_trading_day, "dealer", "dealer", True, next_transition)

    field_phase = _field_phase(day, now_utc)
    if is_trading_day:
        if field_phase is not None:
            is_open = field_phase in TRADABLE_PHASES
            return ExchangeSession(
                exchange_name, True, date_text, True,
                field_phase if is_open else "closed", field_phase, is_open, next_transition,
            )
        if active_intervals:
            # Prefer restrictive phases if an interval overlaps a clearing window.
            phases = [item[1] for item in active_intervals]
            phase = "clearing" if "clearing" in phases else phases[0]
            is_open = phase in TRADABLE_PHASES
            return ExchangeSession(
                exchange_name, True, date_text, True,
                phase if is_open else "closed", phase, is_open, next_transition,
            )
        return ExchangeSession(exchange_name, True, date_text, True, "closed", "outside_scheduled_window", False, next_transition)

    # Some official calendars mark a day as non-exchange trading but still return
    # explicit internal trading intervals. Honor only recognized, active intervals.
    non_dealer_trading = next(
        (item for item in active_intervals if item[1] in TRADABLE_PHASES),
        None,
    )
    if non_dealer_trading is not None:
        phase = non_dealer_trading[1]
        return ExchangeSession(exchange_name, True, date_text, False, phase, phase, True, next_transition)
    return ExchangeSession(exchange_name, True, date_text, False, "closed", "calendar_closed", False, next_transition)
