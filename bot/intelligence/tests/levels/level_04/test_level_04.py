import unittest
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_04.level_04_engine import Level4Engine


class TestLevel4(unittest.TestCase):
    def snapshot(self, price=105.0, previous=100.0, volume=1500.0, average=1000.0):
        return MarketSnapshot(
            symbol="TEST", price=price, previous_price=previous, volume=volume,
            average_volume=average, volatility=0.02, momentum=0.03, liquidity=0.8,
        )

    def test_all_six_analyzers_run(self):
        result = Level4Engine().analyze(self.snapshot())
        self.assertEqual(len(result.analyzer_results), 6)
        self.assertTrue(0.0 <= result.score <= 1.0)
        self.assertTrue(0.0 <= result.confidence <= 1.0)

    def test_buying_pressure_exceeds_selling_on_rising_price(self):
        result = Level4Engine().analyze(self.snapshot(price=105, previous=100))
        self.assertGreater(result.buying_pressure, result.selling_pressure)
        self.assertGreater(result.pressure_balance, 0.5)

    def test_selling_pressure_exceeds_buying_on_falling_price(self):
        result = Level4Engine().analyze(self.snapshot(price=95, previous=100))
        self.assertGreater(result.selling_pressure, result.buying_pressure)
        self.assertLess(result.pressure_balance, 0.5)

    def test_missing_average_volume_is_flagged_without_failure(self):
        result = Level4Engine().analyze(self.snapshot(volume=0, average=0))
        self.assertTrue(result.confidence < 0.7)
        self.assertIn("historical_flow_not_available", result.warnings)

    def test_behavior_layer_does_not_mutate_snapshot(self):
        snapshot = self.snapshot()
        before = snapshot
        Level4Engine().analyze(snapshot)
        self.assertEqual(snapshot, before)


if __name__ == "__main__":
    unittest.main()
