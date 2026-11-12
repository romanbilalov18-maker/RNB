import unittest
from datetime import datetime, timezone

from bot.models import VirtualTrade
from bot.intelligence.levels.level_06.analyzers.expected_value import (
    calculate_expected_value,
    estimate_expected_value,
)


class ExpectedValueTests(unittest.TestCase):
    def test_calculates_gross_expectancy(self):
        result = calculate_expected_value(0.6, 0.04, 0.02)
        self.assertAlmostEqual(result, 0.016)

    def test_rejects_invalid_formula_inputs(self):
        invalid_cases = (
            (True, 0.04, 0.02),
            (1.1, 0.04, 0.02),
            (0.5, -0.01, 0.02),
            (0.5, 0.04, float("nan")),
        )
        for args in invalid_cases:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    calculate_expected_value(*args)

    def test_estimates_from_completed_sell_events_and_reverses_commissions(self):
        timestamp = datetime(2026, 11, 1, tzinfo=timezone.utc)
        trades = []
        # 12 gross winners at +4%; 8 gross losers at -2%.
        # Entry and exit commissions are already deducted from realized P&L.
        for index in range(12):
            entry_notional = 1_000.0
            gross_pnl = 40.0
            entry_fee = entry_notional * 0.001
            exit_fee = 1_040.0 * 0.001
            trades.append(VirtualTrade(
                timestamp, f"W{index}", "SELL", 10, 104.0,
                exit_fee, gross_pnl - entry_fee - exit_fee,
                entry_price=100.0,
            ))
        for index in range(8):
            entry_notional = 1_000.0
            gross_pnl = -20.0
            entry_fee = entry_notional * 0.001
            exit_fee = 980.0 * 0.001
            trades.append(VirtualTrade(
                timestamp, f"L{index}", "SELL", 10, 98.0,
                exit_fee, gross_pnl - entry_fee - exit_fee,
                entry_price=100.0,
            ))
        trades.append(VirtualTrade(
            timestamp, "OPEN", "BUY", 10, 100.0, 1.0, 0.0,
            entry_price=100.0,
        ))

        estimate = estimate_expected_value(
            trades, commission_rate=0.001, minimum_samples=20
        )

        self.assertTrue(estimate.available)
        self.assertEqual(estimate.sample_count, 20)
        self.assertEqual(estimate.wins, 12)
        self.assertEqual(estimate.losses, 8)
        self.assertAlmostEqual(estimate.win_probability, 0.6)
        self.assertAlmostEqual(estimate.average_win_return, 0.04)
        self.assertAlmostEqual(estimate.average_loss_return, 0.02)
        self.assertAlmostEqual(estimate.expected_gross_return, 0.016)
        self.assertEqual(estimate.reason, "shadow_estimate_ready")

    def test_returns_unavailable_when_history_is_too_short(self):
        timestamp = datetime(2026, 11, 1, tzinfo=timezone.utc)
        trades = [
            VirtualTrade(timestamp, "A", "SELL", 1, 101.0, 0.1, 0.8, entry_price=100.0)
        ]
        estimate = estimate_expected_value(
            trades, commission_rate=0.001, minimum_samples=20
        )
        self.assertFalse(estimate.available)
        self.assertEqual(estimate.reason, "insufficient_history")
        self.assertIsNone(estimate.expected_gross_return)

    def test_requires_both_win_and_loss_classes(self):
        timestamp = datetime(2026, 11, 1, tzinfo=timezone.utc)
        trades = [
            VirtualTrade(timestamp, str(index), "SELL", 1, 110.0, 0.1, 9.8,
                         entry_price=100.0)
            for index in range(20)
        ]
        estimate = estimate_expected_value(
            trades, commission_rate=0.001, minimum_samples=20
        )
        self.assertFalse(estimate.available)
        self.assertEqual(estimate.reason, "both_win_and_loss_outcomes_required")

    def test_ignores_buys_and_excludes_malformed_sell_events(self):
        timestamp = datetime(2026, 11, 1, tzinfo=timezone.utc)
        trades = [
            VirtualTrade(timestamp, "BUY", "BUY", 1, 100.0, 0.1, 0.0,
                         entry_price=100.0),
            VirtualTrade(timestamp, "BAD", "SELL", 1, 100.0, 0.1, 0.0,
                         entry_price=None),
        ]
        estimate = estimate_expected_value(
            trades, commission_rate=0.001, minimum_samples=1
        )
        self.assertEqual(estimate.sample_count, 0)
        self.assertEqual(estimate.excluded_count, 1)
        self.assertFalse(estimate.available)

    def test_rejects_invalid_configuration(self):
        for rate in (True, -0.1, 1.0, float("inf")):
            with self.subTest(rate=rate):
                with self.assertRaises(ValueError):
                    estimate_expected_value([], commission_rate=rate)
        for minimum in (True, 0, -1, 1.5):
            with self.subTest(minimum=minimum):
                with self.assertRaises(ValueError):
                    estimate_expected_value([], commission_rate=0.001,
                                            minimum_samples=minimum)


if __name__ == "__main__":
    unittest.main()
