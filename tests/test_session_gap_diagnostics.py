import unittest
from datetime import date

from bot.intelligence.levels.level_01.session_gap_diagnostics import find_missing_trading_dates


class SessionGapDiagnosticsTests(unittest.TestCase):
    def test_only_flags_missing_dates_in_official_trading_calendar(self):
        # Calendar includes only official sessions; weekend/holiday dates are omitted.
        official = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
        observed = ["2026-01-02", "2026-01-06"]
        self.assertEqual(
            find_missing_trading_dates(official, observed),
            ["2026-01-05", "2026-01-07"],
        )

    def test_accepts_date_objects_and_iso_timestamps(self):
        official = [date(2026, 1, 2), "2026-01-05T10:00:00+00:00"]
        observed = ["2026-01-02T15:00:00Z"]
        self.assertEqual(find_missing_trading_dates(official, observed), ["2026-01-05"])

    def test_utc_timestamp_after_21_00_maps_to_next_moscow_session_date(self):
        # 21:30 UTC is 00:30 on the following date in Moscow (UTC+3).
        self.assertEqual(
            find_missing_trading_dates(
                ["2026-01-06"],
                ["2026-01-05T21:30:00Z"],
            ),
            [],
        )

    def test_offset_aware_calendar_and_candle_timestamps_share_moscow_date(self):
        self.assertEqual(
            find_missing_trading_dates(
                ["2026-01-05T21:30:00Z"],
                ["2026-01-06T00:30:00+03:00"],
            ),
            [],
        )

    def test_naive_timestamps_are_treated_as_utc_before_moscow_conversion(self):
        self.assertEqual(
            find_missing_trading_dates(
                ["2026-01-06"],
                [__import__("datetime").datetime(2026, 1, 5, 21, 30)],
            ),
            [],
        )

    def test_does_not_invent_expected_dates_when_calendar_is_empty(self):
        self.assertEqual(find_missing_trading_dates([], ["2026-01-03"]), [])

    def test_rejects_invalid_calendar_values(self):
        with self.assertRaisesRegex(ValueError, "invalid ISO"):
            find_missing_trading_dates(["not-a-date"], [])


if __name__ == "__main__":
    unittest.main()
