import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from bot.market_context import build_market_context
from bot.market_context.clock import current_times
from bot.market_context.calendar import weekday_candidate
from bot.market_context.instrument_status import is_instrument_active
from bot.market_context.quote_validator import is_fresh_quote

class MarketContextTests(unittest.TestCase):
    def test_clock_normalizes_to_utc_and_moscow(self):
        utc, moscow = current_times(datetime(2026, 10, 19, 6, 0, tzinfo=timezone.utc))
        self.assertEqual(utc.hour, 6)
        self.assertEqual(moscow.hour, 9)
        self.assertEqual(str(moscow.tzinfo), "Europe/Moscow")

    def test_naive_clock_is_rejected(self):
        with self.assertRaises(ValueError):
            current_times(datetime(2026, 10, 19, 9, 0))

    def test_weekday_does_not_mean_exchange_open(self):
        monday = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
        context = build_market_context(monday)
        self.assertTrue(context.weekday_candidate)
        self.assertEqual(context.session, "unknown")
        self.assertFalse(context.broker_status_verified)

    def test_weekend_candidate(self):
        sunday = datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc)
        self.assertFalse(weekday_candidate(sunday.astimezone(ZoneInfo("Europe/Moscow"))))
        context = build_market_context(sunday, {"id": "NORMAL_TRADING"}, status_check_succeeded=True)
        self.assertEqual(context.session, "unknown")
        self.assertEqual(context.session_phase, "schedule_unavailable")
        self.assertEqual(context.broker_active_instruments, 1)
        self.assertTrue(context.broker_status_verified)
        self.assertFalse(context.schedule_verified)

    def test_weekend_session_can_open_only_when_official_schedule_confirms_it(self):
        sunday = datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc)
        scheduled = SimpleNamespace(
            verified=True, is_open=True, session="dealer", phase="dealer",
            next_transition=datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc),
            to_dict=lambda: {"exchange": "MOEX_WEEKEND", "session": "dealer", "phase": "dealer", "verified": True, "is_open": True},
        )
        context = build_market_context(
            sunday,
            {"id": "DEALER_NORMAL_TRADING"},
            status_check_succeeded=True,
            exchange_sessions={"MOEX_WEEKEND": scheduled},
            schedule_check_succeeded=True,
        )
        self.assertFalse(context.weekday_candidate)
        self.assertEqual(context.session, "scheduled_open")
        self.assertEqual(context.session_phase, "dealer")
        self.assertTrue(context.schedule_verified)

    def test_exact_active_tinvest_statuses_count_without_replacing_schedule_gate(self):
        self.assertTrue(is_instrument_active("NORMAL_TRADING"))
        self.assertTrue(is_instrument_active("SESSION_OPEN"))
        self.assertTrue(is_instrument_active("DEALER_NORMAL_TRADING"))
        self.assertFalse(is_instrument_active("BREAK_IN_TRADING"))
        context = build_market_context(
            datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc),
            {"a": "NORMAL_TRADING", "b": "DEALER_NORMAL_TRADING", "c": "SESSION_OPEN"},
            status_check_succeeded=True,
        )
        # This is a broker-status count only; trade eligibility still requires
        # a verified open exchange schedule and a fresh quote in LiveMarketRunner.
        self.assertEqual(context.broker_active_instruments, 3)

    def test_quote_freshness_requires_timestamp(self):
        now = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
        self.assertFalse(is_fresh_quote(None, now, 300))
        self.assertTrue(is_fresh_quote(now, now, 300))

if __name__ == "__main__":
    unittest.main()
