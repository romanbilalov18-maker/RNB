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

        class Candle:
            open = 100.0
            high = 105.0
            low = 99.0
            close = 103.0
            volume = 1800

        snapshot = _build_snapshot(Analysis(), 104.0, 103.0, 100, Candle())
        self.assertIsInstance(snapshot, MarketSnapshot)
        self.assertEqual(snapshot.symbol, "TEST")
        self.assertEqual(snapshot.price, 104.0)
        self.assertEqual(snapshot.previous_price, 103.0)
        self.assertEqual(snapshot.average_volume, 1000.0)
        self.assertEqual(snapshot.volume, 1800.0)
        self.assertEqual(snapshot.momentum, 0.04)
        self.assertEqual(snapshot.volatility, 0.02)
        self.assertEqual(snapshot.liquidity, 0.75)
        self.assertEqual(snapshot.open_price, 100.0)
        self.assertEqual(snapshot.high_price, 105.0)
        self.assertEqual(snapshot.low_price, 99.0)
        self.assertEqual(snapshot.close_price, 103.0)
        self.assertEqual(snapshot.candle_volume, 1800.0)
        self.assertAlmostEqual(snapshot.candle_range, 6.0 / 103.0)
        self.assertAlmostEqual(snapshot.close_position, 4.0 / 6.0)
        self.assertAlmostEqual(snapshot.volume_ratio, 1.8)
        self.assertEqual(snapshot.lot_size, 100)

    def test_missing_candle_does_not_invent_ohlcv(self):
        class Analysis:
            ticker = "TEST"
            average_volume = 1000.0
            volume_ratio = 1.5
            volatility = 0.02
            momentum = 0.04

        snapshot = _build_snapshot(Analysis(), 104.0, 103.0, 100)
        self.assertIsNone(snapshot.open_price)
        self.assertIsNone(snapshot.high_price)
        self.assertIsNone(snapshot.low_price)
        self.assertIsNone(snapshot.close_price)
        self.assertIsNone(snapshot.candle_volume)
        self.assertIsNone(snapshot.candle_range)
        self.assertIsNone(snapshot.close_position)
        self.assertIsNone(snapshot.volume_ratio)


if __name__ == "__main__":
    unittest.main()
