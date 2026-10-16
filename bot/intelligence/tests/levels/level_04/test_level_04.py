import math
import unittest

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_04.level_04_engine import Level4Engine
from bot.intelligence.levels.level_04.analyzers import accumulation, distribution, buying_pressure, selling_pressure


class TestLevel4(unittest.TestCase):
    def snapshot(self, price=105.0, previous=100.0, volume=1500.0, average=1000.0, **kwargs):
        values = dict(
            symbol="TEST", price=price, previous_price=previous, volume=volume,
            average_volume=average, volatility=0.02, momentum=0.03, liquidity=0.8,
        )
        values.update(kwargs)
        return MarketSnapshot(**values)

    def test_all_six_analyzers_run_and_scores_are_bounded(self):
        result = Level4Engine().analyze(self.snapshot())
        self.assertEqual(len(result.analyzer_results), 6)
        for value in (
            result.score, result.confidence, result.consistency, result.buying_pressure,
            result.selling_pressure, result.pressure_balance, result.accumulation,
            result.distribution, result.abnormal_activity, result.liquidity_behavior,
        ):
            self.assertTrue(math.isfinite(value))
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_buying_pressure_exceeds_selling_on_rising_price(self):
        result = Level4Engine().analyze(self.snapshot(price=105, previous=100))
        self.assertGreater(result.buying_pressure, result.selling_pressure)
        self.assertGreater(result.pressure_balance, 0.5)

    def test_selling_pressure_exceeds_buying_on_falling_price(self):
        result = Level4Engine().analyze(self.snapshot(price=95, previous=100))
        self.assertGreater(result.selling_pressure, result.buying_pressure)
        self.assertLess(result.pressure_balance, 0.5)

    def test_missing_history_is_reported_without_failure(self):
        result = Level4Engine().analyze(self.snapshot(volume=0, average=0))
        self.assertIn("historical_price_volume_history_insufficient", result.warnings)
        self.assertIn("liquidity_volume_context_unavailable", result.warnings)
        self.assertLess(result.confidence, 0.7)

    def test_history_length_mismatch_is_not_silently_truncated(self):
        snapshot = self.snapshot(historical_returns=(0.01, -0.01, 0.02, -0.02, 0.01),
                                 historical_volume_ratios=(1.0, 2.0, 1.5, 1.2))
        result = accumulation.analyze(snapshot)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("historical_price_volume_history_misaligned", result.warnings)

    def test_invalid_history_values_are_filtered_and_reported(self):
        snapshot = self.snapshot(
            historical_returns=(0.01, -0.01, 0.02, -0.02, 0.01, float("nan")),
            historical_volume_ratios=(1.0, 2.0, 1.5, 1.2, 0.8, 1.0),
        )
        result = distribution.analyze(snapshot)
        self.assertIn("historical_price_volume_invalid_observations", result.warnings)
        self.assertEqual(result.metadata["observations"], 5)

    def test_invalid_close_position_is_not_used(self):
        snapshot = self.snapshot(close_position=2.0)
        result = buying_pressure.analyze(snapshot)
        self.assertIsNone(result.metadata["close_position"])
        self.assertIn("buying_pressure_partial_inputs", result.warnings)

    def test_invalid_price_is_unavailable(self):
        result = selling_pressure.analyze(self.snapshot(price=float("nan")))
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("price_change_not_available", result.warnings)

    def test_level3_context_is_checked_and_reported(self):
        snapshot = self.snapshot()
        level3 = type("Level3", (), {"symbol": "OTHER", "score": 0.6, "confidence": 0.8})()
        result = Level4Engine().analyze(snapshot, level3)
        self.assertIn("level3_symbol_mismatch", result.warnings)
        self.assertFalse(result.metadata["level3_context_available"])

    def test_behavior_layer_does_not_mutate_snapshot(self):
        snapshot = self.snapshot()
        before = snapshot
        Level4Engine().analyze(snapshot)
        self.assertEqual(snapshot, before)


if __name__ == "__main__":
    unittest.main()
