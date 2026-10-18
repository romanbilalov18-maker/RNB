import unittest
from datetime import datetime, timezone
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
        self.assertEqual(context.session, "closed_by_weekend_calendar")
        self.assertEqual(context.session_phase, "weekend_guard")
        self.assertEqual(context.broker_active_instruments, 1)
        self.assertTrue(context.broker_status_verified)

    def test_only_exact_active_statuses_count(self):
        self.assertTrue(is_instrument_active("NORMAL_TRADING"))
        self.assertFalse(is_instrument_active("DEALER_NORMAL_TRADING"))
        context = build_market_context(datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc), {"a": "NORMAL_TRADING", "b": "DEALER_NORMAL_TRADING"}, status_check_succeeded=True)
        self.assertEqual(context.broker_active_instruments, 1)

    def test_quote_freshness_requires_timestamp(self):
        now = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
        self.assertFalse(is_fresh_quote(None, now, 300))
        self.assertTrue(is_fresh_quote(now, now, 300))

if __name__ == "__main__":
    unittest.main()
