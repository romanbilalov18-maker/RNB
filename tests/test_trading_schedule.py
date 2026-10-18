import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from bot.market_context.trading_schedule import resolve_exchange_session


def stamp(hour, minute=0, day=19):
    return datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc)


def interval(kind, start, end):
    return SimpleNamespace(
        type=kind,
        interval=SimpleNamespace(start_ts=start, end_ts=end),
    )


def trading_day(day_number, trading=True, **values):
    defaults = {
        "date": datetime(2026, 10, day_number, 0, 0, tzinfo=timezone.utc),
        "is_trading_day": trading,
        "start_time": stamp(6, day=day_number),
        "end_time": stamp(16, day=day_number),
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
    defaults.update(values)
    return SimpleNamespace(**defaults)


class TradingScheduleTests(unittest.TestCase):
    def test_main_session_is_open_inside_official_window(self):
        day = trading_day(19)
        session = resolve_exchange_session(
            "MOEX", SimpleNamespace(exchange="MOEX", days=[day]), stamp(10),
        )
        self.assertTrue(session.verified)
        self.assertTrue(session.is_open)
        self.assertEqual(session.phase, "main")
        self.assertEqual(session.schedule_date, "2026-10-19")

    def test_outside_official_window_is_closed(self):
        day = trading_day(19)
        session = resolve_exchange_session(
            "MOEX", SimpleNamespace(exchange="MOEX", days=[day]), stamp(18),
        )
        self.assertTrue(session.verified)
        self.assertFalse(session.is_open)
        self.assertEqual(session.phase, "outside_scheduled_window")

    def test_clearing_overrides_broad_main_window(self):
        day = trading_day(
            19,
            clearing_start_time=stamp(10, day=19),
            clearing_end_time=stamp(11, day=19),
        )
        session = resolve_exchange_session(
            "MOEX", SimpleNamespace(exchange="MOEX", days=[day]), stamp(10, 30),
        )
        self.assertFalse(session.is_open)
        self.assertEqual(session.phase, "clearing")

    def test_dealer_interval_can_open_on_exchange_non_trading_date(self):
        day = trading_day(
            18,
            trading=False,
            start_time=None,
            end_time=None,
            intervals=[interval("dealer_regular_trading_session", stamp(8, day=18), stamp(12, day=18))],
        )
        session = resolve_exchange_session(
            "MOEX_WEEKEND", SimpleNamespace(exchange="MOEX_WEEKEND", days=[day]), stamp(9, day=18),
        )
        self.assertTrue(session.verified)
        self.assertTrue(session.is_open)
        self.assertEqual(session.phase, "dealer")

    def test_unknown_or_missing_exchange_schedule_fails_closed(self):
        now = stamp(10)
        missing = resolve_exchange_session("UNKNOWN", None, now)
        no_current_day = resolve_exchange_session(
            "MOEX", SimpleNamespace(exchange="MOEX", days=[trading_day(20)]), now,
        )
        self.assertFalse(missing.verified)
        self.assertFalse(missing.is_open)
        self.assertFalse(no_current_day.verified)
        self.assertFalse(no_current_day.is_open)

    def test_evening_session_is_distinguished(self):
        day = trading_day(
            19,
            evening_start_time=stamp(16, day=19),
            evening_end_time=stamp(20, day=19),
        )
        session = resolve_exchange_session(
            "MOEX_PLUS", SimpleNamespace(exchange="MOEX_PLUS", days=[day]), stamp(18),
        )
        self.assertTrue(session.is_open)
        self.assertEqual(session.phase, "evening")


if __name__ == "__main__":
    unittest.main()
