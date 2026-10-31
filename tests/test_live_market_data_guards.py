import unittest
from datetime import datetime, timedelta, timezone

from bot.live_runner import LiveMarketRunner
from bot.market_context.trading_schedule import ExchangeSession


class LiveMarketDataGuardTests(unittest.TestCase):

    def test_buy_screen_rejects_illiquid_or_stagnant_candidates(self):
        base = dict(
            average_volume=1000.0,
            volume_ratio=1.0,
            spread_ticks=2.0,
            position_health_status="NORMAL_MONITORING",
        )
        self.assertIsNone(LiveMarketRunner._buy_candidate_rejection_reason(**base))
        cases = [
            ({"average_volume": 0.0}, "zero_or_invalid_historical_volume"),
            ({"volume_ratio": 0.01}, "recent_volume_below_10_percent_of_history"),
            ({"spread_ticks": None}, "top_of_book_spread_unverified"),
            ({"spread_ticks": 11.0}, "top_of_book_spread_too_wide"),
            ({"position_health_status": "PROLONGED_STAGNATION"}, "prolonged_price_stagnation"),
            ({"buy_available": False}, "broker_buy_unavailable_or_unverified"),
            ({"buy_available": None}, "broker_buy_unavailable_or_unverified"),
        ]
        for changes, expected in cases:
            with self.subTest(changes=changes):
                args = {**base, **changes}
                reason = LiveMarketRunner._buy_candidate_rejection_reason(**args)
                self.assertIsNotNone(reason)
                self.assertIn(expected, reason)

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

    def test_quote_item_freshness_rejects_missing_stale_and_far_future_timestamps(self):
        now = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
        fresh = type("Quote", (), {"time": now - timedelta(seconds=300)})()
        stale = type("Quote", (), {"time": now - timedelta(seconds=301)})()
        future = type("Quote", (), {"time": now + timedelta(seconds=61)})()
        missing = type("Quote", (), {})()

        self.assertTrue(LiveMarketRunner._quote_item_is_fresh(fresh, now, 300))
        self.assertFalse(LiveMarketRunner._quote_item_is_fresh(stale, now, 300))
        self.assertFalse(LiveMarketRunner._quote_item_is_fresh(future, now, 300))
        self.assertFalse(LiveMarketRunner._quote_item_is_fresh(missing, now, 300))
        self.assertFalse(LiveMarketRunner._quote_item_is_fresh(None, now, 300))

    def test_fresh_quote_with_timezone_is_accepted(self):
        now = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
        quote = now - timedelta(seconds=120)
        age, reason = LiveMarketRunner._quote_freshness(quote, now, 300)
        self.assertEqual(reason, "fresh")
        self.assertEqual(age, 120)

    def test_quote_age_at_or_below_limit_is_accepted(self):
        now = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
        for seconds in (299, 300):
            with self.subTest(age_seconds=seconds):
                age, reason = LiveMarketRunner._quote_freshness(
                    now - timedelta(seconds=seconds), now, 300
                )
                self.assertEqual(reason, "fresh")
                self.assertEqual(age, seconds)

    def test_quote_older_than_limit_is_rejected(self):
        now = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
        for seconds in (301, 3600, 3 * 3600):
            with self.subTest(age_seconds=seconds):
                age, reason = LiveMarketRunner._quote_freshness(
                    now - timedelta(seconds=seconds), now, 300
                )
                self.assertEqual(reason, "stale_quote")
                self.assertEqual(age, seconds)

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
