"""Readiness checks for date, exchange-open state, and trading-session detection.

These are deterministic unit tests against broker-shaped schedule data; they do not
place orders or claim that a live T-Invest schedule endpoint was reachable.
"""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from bot.market_context.session_manager import build_market_context
from bot.market_context.trading_schedule import resolve_exchange_session


UTC = timezone.utc
MOSCOW = ZoneInfo("Europe/Moscow")


def ts(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


def make_day(day: int, *, trading: bool = True, **overrides):
    fields = {
        "date": ts(day, 0),
        "is_trading_day": trading,
        "start_time": ts(day, 6) if trading else None,
        "end_time": ts(day, 16) if trading else None,
        "opening_auction_start_time": None,
        "opening_auction_end_time": None,
        "closing_auction_start_time": None,
        "closing_auction_end_time": None,
        "evening_opening_auction_start_time": None,
        "evening_start_time": None,
        "evening_end_time": None,
        "premarket_start_time": None,
        "premarket_end_time": None,
        "clearing_start_time": None,
        "clearing_end_time": None,
        "intervals": [],
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def schedule(day, exchange="MOEX"):
    return SimpleNamespace(exchange=exchange, days=[day])


class MarketCalendarSessionReadinessTests(unittest.TestCase):
    """Check the bot's interpretation of date, schedule, and session phase."""

    def test_reports_calendar_date_and_weekday_in_moscow_time(self):
        context = build_market_context(ts(19, 21))
        self.assertEqual(context.observed_at_moscow.date().isoformat(), "2026-10-20")
        self.assertEqual(context.weekday, "Tuesday")
        self.assertEqual(context.weekday_number, 1)

    def test_weekday_and_official_open_window_resolve_to_main_session(self):
        session = resolve_exchange_session("MOEX", schedule(make_day(19)), ts(19, 10))
        self.assertTrue(session.verified)
        self.assertTrue(session.is_open)
        self.assertEqual(session.schedule_date, "2026-10-19")
        self.assertEqual(session.phase, "main")

    def test_official_non_trading_day_resolves_to_closed(self):
        session = resolve_exchange_session(
            "MOEX", schedule(make_day(18, trading=False)), ts(18, 10)
        )
        self.assertTrue(session.verified)
        self.assertFalse(session.is_open)
        self.assertEqual(session.phase, "calendar_closed")

    def test_explicit_tinvest_weekend_exchange_is_labeled_as_weekend_session(self):
        session = resolve_exchange_session(
            "moex_mrng_evng_e_wknd_dlr",
            schedule(make_day(18, trading=True), exchange="moex_mrng_evng_e_wknd_dlr"),
            ts(18, 10),
        )
        self.assertTrue(session.verified)
        self.assertTrue(session.is_open)
        self.assertEqual(session.phase, "weekend")

    def test_outside_session_window_resolves_to_closed(self):
        session = resolve_exchange_session("MOEX", schedule(make_day(19)), ts(19, 18))
        self.assertTrue(session.verified)
        self.assertFalse(session.is_open)
        self.assertEqual(session.phase, "outside_scheduled_window")

    def test_evening_session_is_identified(self):
        day = make_day(
            19,
            evening_start_time=ts(19, 16),
            evening_end_time=ts(19, 20),
        )
        session = resolve_exchange_session("MOEX", schedule(day), ts(19, 18))
        self.assertTrue(session.is_open)
        self.assertEqual(session.phase, "evening")

    def test_clearing_blocks_trading_even_inside_main_window(self):
        day = make_day(
            19,
            clearing_start_time=ts(19, 10),
            clearing_end_time=ts(19, 11),
        )
        session = resolve_exchange_session("MOEX", schedule(day), ts(19, 10, 30))
        self.assertFalse(session.is_open)
        self.assertEqual(session.phase, "clearing")

    def test_missing_schedule_fails_closed(self):
        session = resolve_exchange_session("MOEX", None, ts(19, 10))
        self.assertFalse(session.verified)
        self.assertFalse(session.is_open)
        self.assertEqual(session.phase, "schedule_missing")

    def test_schedule_without_current_date_fails_closed(self):
        session = resolve_exchange_session(
            "MOEX", schedule(make_day(20)), ts(19, 10)
        )
        self.assertFalse(session.verified)
        self.assertFalse(session.is_open)
        self.assertEqual(session.phase, "current_day_not_returned")

    def test_market_context_does_not_claim_open_without_verified_schedule(self):
        context = build_market_context(
            ts(19, 10),
            {"instrument": "NORMAL_TRADING"},
            status_check_succeeded=True,
            exchange_sessions={},
            schedule_check_succeeded=False,
        )
        self.assertEqual(context.session, "unknown")
        self.assertEqual(context.session_phase, "schedule_unavailable")
        self.assertFalse(context.schedule_verified)


if __name__ == "__main__":
    unittest.main()
