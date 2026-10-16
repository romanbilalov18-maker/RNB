import unittest

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result
from bot.intelligence.levels.level_02.analyzers.momentum_structure import analyze as analyze_momentum_structure
from bot.intelligence.levels.level_02.analyzers.trend import analyze as analyze_trend
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


def make_level1(*results, confidence=0.8):
    return Level1Result("TEST", 0.5, confidence, 0.8, tuple(results))


class Level02AnalyzerContractTests(unittest.TestCase):
    def test_trend_uses_same_momentum_scale_as_level1(self):
        result = analyze_trend(MarketSnapshot(symbol="TEST", price=101, previous_price=100, momentum=0.01),
                               make_level1(AnalyzerResult("price", 0.55, 1.0)))
        self.assertAlmostEqual(result.metrics["direction"], 0.55)
        self.assertGreater(result.confidence, 0)

    def test_trend_rejects_boolean_momentum(self):
        result = analyze_trend(MarketSnapshot(symbol="TEST", price=101, previous_price=100, momentum=True),
                               make_level1(AnalyzerResult("price", 0.55, 1.0)))
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("invalid_momentum", result.warnings)

    def test_momentum_structure_exposes_inputs_and_difference(self):
        result = analyze_momentum_structure(
            MarketSnapshot(symbol="TEST", price=101, previous_price=100, momentum=0.01),
            make_level1(AnalyzerResult("momentum", 0.55, 1.0)))
        self.assertAlmostEqual(result.metrics["price_change"], 0.01)
        self.assertAlmostEqual(result.metrics["absolute_difference"], 0.0)
        self.assertAlmostEqual(result.metrics["alignment"], 1.0)

    def test_momentum_structure_rejects_non_finite_momentum(self):
        result = analyze_momentum_structure(
            MarketSnapshot(symbol="TEST", price=101, previous_price=100, momentum=float("nan")),
            make_level1(AnalyzerResult("momentum", 0.55, 1.0)))
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("invalid_momentum", result.warnings)

    def test_level2_result_rejects_bool_and_non_finite_fields(self):
        for value in (True, float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    Level2Result("TEST", value, 0.5, 0.5)


if __name__ == "__main__":
    unittest.main()
