import unittest
from types import SimpleNamespace
from unittest.mock import patch

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


class LearningPipeline:
    created = []

    def __init__(self, learning_observations=()):
        self.learning_observations = tuple(learning_observations)
        self.created.append(self)

    def analyze(self, snapshot):
        return SimpleNamespace(
            symbol=snapshot.symbol,
            learning_samples=len(self.learning_observations),
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
        self.assertFalse(snapshot.portfolio_context_available)
        self.assertAlmostEqual(snapshot.candle_range, 15.0 / 105.0)
        self.assertAlmostEqual(snapshot.close_position, 10.0 / 15.0)


    def test_passes_real_market_and_portfolio_context(self):
        self.scan.market_return = 0.012
        self.scan.market_breadth = 0.64
        self.scan.market_sample_count = 180
        self.scan.sector_by_ticker = {"AAA": "TECH", "HELD": "TECH"}
        self.scan.sector_returns = {"TECH": 0.018}
        portfolio = SimpleNamespace(
            positions={
                "HELD": SimpleNamespace(quantity=3, average_price=95.0),
            }
        )
        snapshot = build_market_snapshot(
            self.scan, self.scan.analyses["AAA"], portfolio=portfolio
        )
        self.assertEqual(snapshot.market_sample_count, 180)
        self.assertEqual(snapshot.market_breadth, 0.64)
        self.assertEqual(snapshot.sector, "TECH")
        self.assertAlmostEqual(snapshot.sector_return, -0.01)
        self.assertEqual(snapshot.peer_count, 1)
        self.assertEqual(snapshot.portfolio_positions[0]["symbol"], "HELD")
        self.assertEqual(snapshot.portfolio_positions[0]["quantity"], 3)
        self.assertEqual(snapshot.portfolio_positions[0]["market_value"], 297.0)
        self.assertTrue(snapshot.portfolio_context_available)

    def test_does_not_fall_back_to_sector_aggregate_when_peer_prices_are_missing(self):
        self.scan.sector_by_ticker = {"AAA": "TECH"}
        self.scan.sector_returns = {"TECH": 0.25}
        snapshot = build_market_snapshot(self.scan, self.scan.analyses["AAA"])
        self.assertIsNone(snapshot.sector_return)
        self.assertIsNone(snapshot.peer_return)
        self.assertEqual(snapshot.peer_count, 0)

    def test_builds_real_market_context_from_scan_history(self):
        self.scan.market_return = 0.012
        self.scan.market_breadth = 0.64
        self.scan.market_sample_count = 180
        self.scan.sector_by_ticker = {"AAA": "TECH", "HELD": "TECH"}
        self.scan.sector_returns = {"TECH": 0.018}
        self.scan.candle_history = {
            "AAA": [
                SimpleNamespace(time="2026-10-01", close=100.0, volume=1000),
                SimpleNamespace(time="2026-10-02", close=102.0, volume=1100),
            ],
            "HELD": [
                SimpleNamespace(time="2026-10-01", close=50.0, volume=500),
                SimpleNamespace(time="2026-10-02", close=51.0, volume=550),
            ],
        }
        snapshot = build_market_snapshot(self.scan, self.scan.analyses["AAA"])
        self.assertAlmostEqual(snapshot.market_return, 0.012)
        self.assertAlmostEqual(snapshot.market_breadth, 0.64)
        self.assertEqual(snapshot.market_sample_count, 180)
        self.assertEqual(snapshot.sector, "TECH")
        self.assertAlmostEqual(snapshot.sector_return, -0.01)
        self.assertEqual(len(snapshot.historical_returns), 1)
        self.assertAlmostEqual(snapshot.historical_returns[0], 0.02)
        self.assertEqual(snapshot.historical_return_dates, ("2026-10-02",))
        self.assertEqual(snapshot.peer_count, 1)

    def test_analyzes_candidates_and_held_positions_once(self):
        pipeline = FakePipeline()
        results = analyze_scan(self.scan, pipeline)
        self.assertEqual(set(results), {"AAA", "HELD"})
        self.assertEqual(sorted(pipeline.symbols), ["AAA", "HELD"])

    def test_skips_ticker_without_fresh_price_context(self):
        self.scan.current_prices.pop("HELD")
        results = analyze_scan(self.scan, FakePipeline())
        self.assertEqual(set(results), {"AAA"})

    def test_passes_only_each_tickers_learning_history_to_its_pipeline(self):
        LearningPipeline.created = []
        observations = {"AAA": (object(), object()), "HELD": (object(),)}
        with patch("bot.intelligence.integration.IntelligencePipeline", LearningPipeline):
            results = analyze_scan(
                self.scan,
                learning_observations_by_ticker=observations,
            )
        self.assertEqual(results["AAA"].learning_samples, 2)
        self.assertEqual(results["HELD"].learning_samples, 1)
        self.assertEqual(
            {tuple(item.learning_observations) for item in LearningPipeline.created},
            {observations["AAA"], observations["HELD"]},
        )


if __name__ == "__main__":
    unittest.main()
