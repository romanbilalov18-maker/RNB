import unittest
from datetime import datetime, timedelta, timezone

from bot.live_runner import LiveMarketRunner
from bot.market_context.trading_schedule import ExchangeSession


class LiveMarketDataGuardTests(unittest.TestCase):
    def test_explicit_exchange_statuses_are_active(self):
        for status in (
            "SECURITY_TRADING_STATUS_NORMAL_TRADING",
            "SECURITY_TRADING_STATUS_OPENING_PERIOD",
            "SECURITY_TRADING_STATUS_CLOSING_PERIOD",
            "NORMAL_TRADING",
            "OPENING_PERIOD",
            "CLOSING_PERIOD",
        ):
            with self.subTest(status=status):
                self.assertTrue(LiveMarketRunner._is_active_trading_status(status))

    def test_dealer_and_non_trading_statuses_are_not_active(self):
        for status in (
            "SECURITY_TRADING_STATUS_DEALER_NORMAL_TRADING",
            "DEALER_NORMAL_TRADING",
            "SECURITY_TRADING_STATUS_NOT_AVAILABLE_FOR_TRADING",
            "NOT_AVAILABLE_FOR_TRADING",
            "UNAVAILABLE",
            "",
        ):
            with self.subTest(status=status):
                self.assertFalse(LiveMarketRunner._is_active_trading_status(status))

    def test_status_requires_a_verified_open_exchange_schedule(self):
        open_session = ExchangeSession(
            exchange="MOEX", verified=True, schedule_date="2026-10-19",
            is_trading_day=True, session="main", phase="main", is_open=True,
        )
        closed_session = ExchangeSession(
            exchange="MOEX", verified=True, schedule_date="2026-10-19",
            is_trading_day=True, session="closed", phase="outside_scheduled_window", is_open=False,
        )
        unknown_session = ExchangeSession(
            exchange="MOEX", verified=False, schedule_date=None,
            is_trading_day=None, session="unknown", phase="schedule_missing", is_open=False,
        )
        self.assertTrue(LiveMarketRunner._status_allows_scheduled_session("NORMAL_TRADING", open_session))
        self.assertTrue(LiveMarketRunner._status_allows_scheduled_session("DEALER_NORMAL_TRADING", open_session))
        self.assertFalse(LiveMarketRunner._status_allows_scheduled_session("NORMAL_TRADING", closed_session))
        self.assertFalse(LiveMarketRunner._status_allows_scheduled_session("DEALER_NORMAL_TRADING", unknown_session))
        self.assertFalse(LiveMarketRunner._status_allows_scheduled_session("NOT_AVAILABLE_FOR_TRADING", open_session))

    def test_status_check_is_case_insensitive_but_not_substring_based(self):
        self.assertTrue(
            LiveMarketRunner._is_active_trading_status(
                "security_trading_status_normal_trading"
            )
        )
        self.assertFalse(
            LiveMarketRunner._is_active_trading_status(
                "SOME_PREFIX_NORMAL_TRADING_SUFFIX"
            )
        )

    def test_fresh_quote_with_timezone_is_accepted(self):
        now = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
        quote = now - timedelta(seconds=120)
        age, reason = LiveMarketRunner._quote_freshness(quote, now, 300)
        self.assertEqual(reason, "fresh")
        self.assertEqual(age, 120)

    def test_quote_older_than_limit_is_not_rejected_by_age(self):
        now = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
        quote = now - timedelta(seconds=301)
        age, reason = LiveMarketRunner._quote_freshness(quote, now, 300)
        self.assertEqual(reason, "fresh")
        self.assertEqual(age, 301)

    def test_small_clock_skew_is_tolerated_but_future_timestamp_is_rejected(self):
        now = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
        _, reason = LiveMarketRunner._quote_freshness(
            now + timedelta(seconds=30), now, 300
        )
        self.assertEqual(reason, "fresh")
        _, reason = LiveMarketRunner._quote_freshness(
            now + timedelta(seconds=61), now, 300
        )
        self.assertEqual(reason, "quote_timestamp_in_future")

    def test_naive_timestamps_are_treated_as_utc(self):
        now = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
        quote = datetime(2026, 10, 17, 11, 59)
        age, reason = LiveMarketRunner._quote_freshness(quote, now, 300)
        self.assertEqual(reason, "fresh")
        self.assertEqual(age, 60)


if __name__ == "__main__":
    unittest.main()
