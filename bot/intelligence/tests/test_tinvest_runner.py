import unittest

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.tinvest_runner import _build_snapshot


class TInvestIntelligenceRunnerTests(unittest.TestCase):
    def test_builds_snapshot_from_real_market_analysis(self):
        class Analysis:
            ticker = "TEST"
            last_price = 100.0
            average_volume = 1000.0
            volume_ratio = 1.5
            volatility = 0.02
            momentum = 0.04

        snapshot = _build_snapshot(Analysis(), 101.0, 100)
        self.assertIsInstance(snapshot, MarketSnapshot)
        self.assertEqual(snapshot.symbol, "TEST")
        self.assertEqual(snapshot.price, 101.0)
        self.assertEqual(snapshot.previous_price, 100.0)
        self.assertEqual(snapshot.average_volume, 1000.0)
        self.assertEqual(snapshot.volume, 1500.0)
        self.assertEqual(snapshot.momentum, 0.04)
        self.assertEqual(snapshot.volatility, 0.02)
        self.assertEqual(snapshot.liquidity, 0.75)


if __name__ == "__main__":
    unittest.main()
