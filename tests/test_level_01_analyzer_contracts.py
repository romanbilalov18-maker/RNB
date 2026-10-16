import unittest

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.analyzers import (
    liquidity,
    momentum,
    price,
    volatility,
    volume,
)


class Level01AnalyzerContractTests(unittest.TestCase):
    def test_price_rejects_boolean_prices_consistently_with_quality_check(self):
        result = price.analyze(MarketSnapshot(symbol="TEST", price=True, previous_price=100.0))
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("invalid_price_input", result.warnings)

        result = price.analyze(MarketSnapshot(symbol="TEST", price=100.0, previous_price=False))
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("invalid_price_input", result.warnings)

    def test_all_numeric_analyzers_reject_boolean_values(self):
        cases = (
            (momentum.analyze, {"momentum": True}, "invalid_momentum"),
            (volatility.analyze, {"volatility": False}, "invalid_volatility"),
            (volume.analyze, {"volume": True, "average_volume": 10.0}, "invalid_volume"),
            (volume.analyze, {"volume": 10.0, "average_volume": True}, "invalid_volume"),
            (liquidity.analyze, {"liquidity": True}, "invalid_liquidity"),
        )
        for analyze, fields, warning in cases:
            with self.subTest(fields=fields):
                result = analyze(MarketSnapshot(symbol="TEST", price=100.0, **fields))
                self.assertEqual(result.confidence, 0.0)
                self.assertIn(warning, result.warnings)

    def test_analyzer_result_rejects_boolean_score_and_confidence(self):
        for kwargs in (
            {"score": True, "confidence": 1.0},
            {"score": 0.5, "confidence": False},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                AnalyzerResult("test", **kwargs)

    def test_price_score_boundaries_and_finite_inputs(self):
        up = price.analyze(MarketSnapshot(symbol="TEST", price=120.0, previous_price=100.0))
        down = price.analyze(MarketSnapshot(symbol="TEST", price=80.0, previous_price=100.0))
        invalid = price.analyze(MarketSnapshot(symbol="TEST", price=float("inf"), previous_price=100.0))
        self.assertEqual(up.score, 1.0)
        self.assertEqual(down.score, 0.0)
        self.assertEqual(invalid.confidence, 0.0)
        self.assertIn("invalid_price_input", invalid.warnings)

    def test_missing_data_stays_unknown(self):
        result = momentum.analyze(MarketSnapshot(symbol="TEST", price=100.0, momentum=None))
        self.assertEqual(result.confidence, 0.0)
        self.assertIsNone(result.metrics["momentum"])
        self.assertIn("momentum_missing", result.warnings)


if __name__ == "__main__":
    unittest.main()
