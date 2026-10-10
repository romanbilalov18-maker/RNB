import unittest
from types import SimpleNamespace

from bot.intelligence.integration import analyze_scan, build_market_snapshot


class FakePipeline:
    def __init__(self):
        self.symbols = []

    def analyze(self, snapshot):
        self.symbols.append(snapshot.symbol)
        return SimpleNamespace(
            symbol=snapshot.symbol,
            overall_score=0.6,
            overall_confidence=0.7,
            overall_consistency=0.8,
        )


class IntelligenceIntegrationTests(unittest.TestCase):
    def setUp(self):
        analysis = SimpleNamespace(
            ticker="AAA", average_volume=1000.0, volume_ratio=1.2,
            volatility=0.02, momentum=0.03,
        )
        held = SimpleNamespace(
            ticker="HELD", average_volume=500.0, volume_ratio=0.8,
            volatility=0.03, momentum=-0.01,
        )
        candle = SimpleNamespace(
            open=100.0, high=110.0, low=95.0, close=105.0, volume=1200
        )
        self.scan = SimpleNamespace(
            analyses={"AAA": analysis, "HELD": held},
            buy_candidates=[analysis],
            current_prices={"AAA": 105.0, "HELD": 99.0},
            previous_closes={"AAA": 100.0, "HELD": 100.0},
            lot_sizes={"AAA": 10, "HELD": 1},
            latest_candles={"AAA": candle},
        )

    def test_builds_snapshot_from_live_scan(self):
        snapshot = build_market_snapshot(self.scan, self.scan.analyses["AAA"])
        self.assertEqual(snapshot.symbol, "AAA")
        self.assertEqual(snapshot.price, 105.0)
        self.assertEqual(snapshot.previous_price, 100.0)
        self.assertEqual(snapshot.lot_size, 10)
        self.assertAlmostEqual(snapshot.candle_range, 15.0 / 105.0)
        self.assertAlmostEqual(snapshot.close_position, 10.0 / 15.0)

    def test_analyzes_candidates_and_held_positions_once(self):
        pipeline = FakePipeline()
        results = analyze_scan(self.scan, pipeline)
        self.assertEqual(set(results), {"AAA", "HELD"})
        self.assertEqual(sorted(pipeline.symbols), ["AAA", "HELD"])

    def test_skips_ticker_without_fresh_price_context(self):
        self.scan.current_prices.pop("HELD")
        results = analyze_scan(self.scan, FakePipeline())
        self.assertEqual(set(results), {"AAA"})


if __name__ == "__main__":
    unittest.main()
