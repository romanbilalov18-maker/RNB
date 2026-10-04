import unittest

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.level_01_engine import aggregate, analyze


class Level01EngineTests(unittest.TestCase):
    def test_runs_six_independent_analyzers(self):
        snapshot = MarketSnapshot(
            symbol="TEST",
            price=105.0,
            previous_price=100.0,
            volume=200.0,
            average_volume=100.0,
            volatility=0.10,
            momentum=0.02,
            liquidity=0.80,
        )
        results = analyze(snapshot)
        self.assertEqual(len(results), 6)
        self.assertTrue(all(isinstance(result, AnalyzerResult) for result in results))

    def test_aggregate_is_bounded(self):
        snapshot = MarketSnapshot(symbol="TEST", price=100.0, previous_price=100.0)
        score = aggregate(analyze(snapshot))
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_missing_optional_data_does_not_crash(self):
        results = analyze(MarketSnapshot(symbol="TEST", price=100.0))
        self.assertEqual(len(results), 6)
        self.assertTrue(any("missing" in warning for result in results for warning in result.warnings))


class ModelTests(unittest.TestCase):
    def test_price_change(self):
        snapshot = MarketSnapshot(symbol="TEST", price=110.0, previous_price=100.0)
        self.assertAlmostEqual(snapshot.price_change(), 0.10)

    def test_result_rejects_invalid_score(self):
        with self.assertRaises(ValueError):
            AnalyzerResult("bad", 1.5, 1.0)


if __name__ == "__main__":
    unittest.main()
