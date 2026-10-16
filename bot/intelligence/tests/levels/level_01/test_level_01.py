import unittest

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.analyzers.data_quality import analyze as analyze_data_quality
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

    def test_data_quality_flags_non_finite_and_out_of_range_values(self):
        result = analyze_data_quality(
            MarketSnapshot(
                symbol="TEST",
                price=float("nan"),
                previous_price=-1.0,
                volume=-5.0,
                average_volume=float("inf"),
            )
        )
        self.assertEqual(result.metrics["available_fields"], 0)
        self.assertEqual(
            set(result.metrics["invalid_fields"]),
            {"price", "previous_price", "volume", "average_volume"},
        )
        self.assertEqual(
            set(result.warnings),
            {
                "invalid_price",
                "invalid_previous_price",
                "invalid_volume",
                "invalid_average_volume",
            },
        )


class ModelTests(unittest.TestCase):
    def test_price_change(self):
        snapshot = MarketSnapshot(symbol="TEST", price=110.0, previous_price=100.0)
        self.assertAlmostEqual(snapshot.price_change(), 0.10)

    def test_result_rejects_invalid_score(self):
        with self.assertRaises(ValueError):
            AnalyzerResult("bad", 1.5, 1.0)


if __name__ == "__main__":
    unittest.main()
