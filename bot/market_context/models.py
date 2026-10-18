from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

@dataclass(frozen=True)
class MarketContext:
    """Time and market-session facts for one scan cycle.

    Calendar-derived fields are estimates; broker instrument statuses remain the
    authority for trade eligibility. Unknown is deliberately different from open.
    """
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
    next_transition: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["observed_at_utc"] = self.observed_at_utc.isoformat()
        result["observed_at_moscow"] = self.observed_at_moscow.isoformat()
        return result
