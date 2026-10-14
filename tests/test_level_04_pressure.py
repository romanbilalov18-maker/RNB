import unittest

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_04.analyzers import buying_pressure, selling_pressure, accumulation, distribution


class Level4PressureTests(unittest.TestCase):
    def test_close_near_high_increases_buying_pressure(self):
        baseline = MarketSnapshot(symbol="AAA", price=102.0, previous_price=100.0, volume_ratio=1.0)
        strong_close = MarketSnapshot(
            symbol="AAA", price=102.0, previous_price=100.0,
            volume_ratio=1.0, close_position=0.95,
        )
        baseline_result = buying_pressure.analyze(baseline)
        strong_result = buying_pressure.analyze(strong_close)
        self.assertGreater(strong_result.score, baseline_result.score)
        self.assertGreater(strong_result.confidence, baseline_result.confidence)

    def test_close_near_low_increases_selling_pressure(self):
        baseline = MarketSnapshot(symbol="AAA", price=98.0, previous_price=100.0, volume_ratio=1.0)
        weak_close = MarketSnapshot(
            symbol="AAA", price=98.0, previous_price=100.0,
            volume_ratio=1.0, close_position=0.05,
        )
        baseline_result = selling_pressure.analyze(baseline)
        weak_result = selling_pressure.analyze(weak_close)
        self.assertGreater(weak_result.score, baseline_result.score)
        self.assertGreater(weak_result.confidence, baseline_result.confidence)

    def test_pressure_does_not_add_the_same_volume_bonus_to_both_sides(self):
        low_volume = MarketSnapshot(symbol="AAA", price=101.0, previous_price=100.0, volume_ratio=0.5)
        high_volume = MarketSnapshot(symbol="AAA", price=101.0, previous_price=100.0, volume_ratio=3.0)
        self.assertAlmostEqual(
            buying_pressure.analyze(low_volume).score,
            buying_pressure.analyze(high_volume).score,
        )
        self.assertAlmostEqual(
            selling_pressure.analyze(low_volume).score,
            selling_pressure.analyze(high_volume).score,
        )

    def test_accumulation_and_distribution_require_aligned_price_volume_history(self):
        snapshot = MarketSnapshot(
            symbol="AAA", price=101.0,
            historical_returns=(0.01, -0.02, 0.015, -0.01, 0.02),
            historical_volume_ratios=(1.0, 2.0, 1.5, 0.8, 1.2),
        )
        accumulated = accumulation.analyze(snapshot)
        distributed = distribution.analyze(snapshot)
        self.assertGreater(accumulated.confidence, 0.0)
        self.assertGreater(distributed.confidence, 0.0)
        self.assertGreater(accumulated.score, distributed.score)


if __name__ == "__main__":
    unittest.main()
