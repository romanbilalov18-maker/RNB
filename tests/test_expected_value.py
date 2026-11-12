import unittest
from datetime import datetime, timezone

from bot.models import VirtualTrade
from bot.intelligence.levels.level_06.analyzers.expected_value import (
    calculate_expected_value,
    estimate_expected_value,
)


class ExpectedValueTests(unittest.TestCase):
    def test_calculates_gross_expectancy(self):
        self.assertAlmostEqual(calculate_expected_value(0.6, 0.04, 0.02), 0.016)

    def test_rejects_invalid_formula_inputs(self):
        for args in ((True, 0.04, 0.02), (1.1, 0.04, 0.02),
                     (0.5, -0.01, 0.02), (0.5, 0.04, float("nan"))):
            with self.subTest(args=args), self.assertRaises(ValueError):
                calculate_expected_value(*args)

    def test_aggregates_partial_exits_into_completed_episode_and_uses_actual_fees(self):
        ts = datetime(2026, 11, 1, tzinfo=timezone.utc)
        trades = []
        closed = set()
        for index in range(12):
            episode = f"W{index}"
            closed.add(episode)
            # Two partial exits, same holding lifecycle. Actual entry fees sum
            # to 1.00; exit fees are supplied per fill.
            trades.extend([
                VirtualTrade(ts, episode, "SELL", 4, 104.0, 0.416, 15.184,
                             entry_price=100.0, trade_episode_id=episode,
                             entry_commission=0.4),
                VirtualTrade(ts, episode, "SELL", 6, 104.0, 0.624, 22.776,
                             entry_price=100.0, trade_episode_id=episode,
                             entry_commission=0.6),
            ])
        for index in range(8):
            episode = f"L{index}"
            closed.add(episode)
            trades.append(VirtualTrade(
                ts, episode, "SELL", 10, 98.0, 0.98, -21.98,
                entry_price=100.0, trade_episode_id=episode,
                entry_commission=1.0,
            ))
        result = estimate_expected_value(
            trades, closed_episode_ids=closed, minimum_samples=20
        )
        self.assertTrue(result.available)
        self.assertEqual(result.sample_count, 20)
        self.assertEqual(result.wins, 12)
        self.assertEqual(result.losses, 8)
        self.assertAlmostEqual(result.win_probability, 0.6)
        self.assertAlmostEqual(result.average_win_return, 0.04)
        self.assertAlmostEqual(result.average_loss_return, 0.02)
        self.assertAlmostEqual(result.expected_gross_return, 0.016)

    def test_open_episodes_and_legacy_rows_are_not_used(self):
        ts = datetime(2026, 11, 1, tzinfo=timezone.utc)
        trades = [
            VirtualTrade(ts, "OPEN", "SELL", 1, 110.0, 0.1, 9.8,
                         entry_price=100.0, trade_episode_id="OPEN",
                         entry_commission=0.1),
            VirtualTrade(ts, "LEGACY", "SELL", 1, 110.0, 0.1, 9.8,
                         entry_price=100.0),
        ]
        result = estimate_expected_value(
            trades, closed_episode_ids=set(), minimum_samples=1
        )
        self.assertFalse(result.available)
        self.assertEqual(result.sample_count, 0)
        self.assertEqual(result.excluded_count, 1)

    def test_requires_explicit_closed_episode_state(self):
        with self.assertRaises(ValueError):
            estimate_expected_value([], minimum_samples=1)

    def test_requires_both_win_and_loss_classes(self):
        ts = datetime(2026, 11, 1, tzinfo=timezone.utc)
        trades = [
            VirtualTrade(ts, str(i), "SELL", 1, 110.0, 0.1, 9.8,
                         entry_price=100.0, trade_episode_id=str(i),
                         entry_commission=0.1)
            for i in range(20)
        ]
        result = estimate_expected_value(
            trades, closed_episode_ids={str(i) for i in range(20)},
            minimum_samples=20,
        )
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "both_win_and_loss_outcomes_required")

    def test_rejects_invalid_configuration(self):
        for minimum in (True, 0, -1, 1.5):
            with self.subTest(minimum=minimum), self.assertRaises(ValueError):
                estimate_expected_value([], closed_episode_ids=set(), minimum_samples=minimum)


if __name__ == "__main__":
    unittest.main()
