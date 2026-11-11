from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from bot.protective_stops import (
    average_true_range,
    initial_atr_stop,
    ratchet_trailing_stop,
)


class ProtectiveStopCalculationTests(unittest.TestCase):
    def test_atr_uses_only_completed_real_candles(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        candles = [
            SimpleNamespace(
                time=start + timedelta(days=index),
                open=100.0 + index,
                high=102.0 + index,
                low=99.0 + index,
                close=101.0 + index,
                is_complete=True,
            )
            for index in range(16)
        ]
        candles.append(SimpleNamespace(
            time=start + timedelta(days=16), high=1000.0, low=1.0,
            close=500.0, is_complete=False,
        ))

        self.assertAlmostEqual(average_true_range(candles, period=14), 3.0)

    def test_atr_requires_period_plus_one_verified_candles(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        candles = [
            SimpleNamespace(
                time=start + timedelta(days=index), high=102.0,
                low=99.0, close=101.0, is_complete=True,
            )
            for index in range(14)
        ]
        self.assertIsNone(average_true_range(candles, period=14))

    def test_atr_rejects_malformed_completed_bar(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        candles = [
            SimpleNamespace(
                time=start + timedelta(days=index), high=102.0,
                low=99.0, close=101.0, is_complete=True,
            )
            for index in range(15)
        ]
        candles[-1].low = 103.0
        self.assertIsNone(average_true_range(candles, period=14))

    def test_initial_stop_and_trailing_stop_are_positive_and_monotonic(self):
        self.assertEqual(initial_atr_stop(100.0, 2.0, 2.0), 96.0)
        self.assertEqual(ratchet_trailing_stop(96.0, 110.0, 2.0, 2.0), 106.0)
        self.assertEqual(ratchet_trailing_stop(106.0, 105.0, 2.0, 2.0), 106.0)

    def test_rejects_invalid_stop_inputs(self):
        with self.assertRaises(ValueError):
            initial_atr_stop(100.0, 60.0, 2.0)
        with self.assertRaises(ValueError):
            ratchet_trailing_stop(0.0, 100.0, 2.0)


if __name__ == "__main__":
    unittest.main()
