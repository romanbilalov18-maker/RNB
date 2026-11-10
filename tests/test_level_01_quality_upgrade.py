import unittest

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.levels.level_01.level_01_engine import aggregate, alpha_results, risk_results
from bot.intelligence.levels.level_01.analyzers.data_quality import analyze


class Level01DataQualityUpgradeTests(unittest.TestCase):
    def test_missing_and_invalid_inputs_are_reported_separately(self):
        result = analyze(MarketSnapshot(
            symbol="TEST",
            price=100.0,
            previous_price=None,
            volume=-1.0,
            average_volume=None,
            volatility=0.02,
            momentum=float("nan"),
            liquidity=None,
        ))
        self.assertEqual(set(result.metrics["missing_fields"]), {
            "previous_price", "average_volume", "liquidity"
        })
        self.assertEqual(set(result.metrics["invalid_fields"]), {"volume", "momentum"})
        self.assertEqual(result.metrics["total_fields"], 7)
        self.assertEqual(result.metrics["available_fields"], 2)
        self.assertAlmostEqual(result.metrics["completeness"], 2 / 7)
        self.assertIn("missing_previous_price", result.warnings)
        self.assertIn("invalid_volume", result.warnings)

    def test_boolean_values_are_not_accepted_as_numeric_market_data(self):
        result = analyze(MarketSnapshot(
            symbol="TEST",
            price=True,
            previous_price=100.0,
            volume=10.0,
            average_volume=10.0,
            volatility=0.01,
            momentum=0.02,
            liquidity=0.5,
        ))
        self.assertIn("price", result.metrics["invalid_fields"])
        self.assertIn("invalid_price", result.warnings)

    def test_complete_valid_snapshot_has_full_completeness(self):
        result = analyze(MarketSnapshot(
            symbol="TEST",
            price=101.0,
            previous_price=100.0,
            volume=120.0,
            average_volume=100.0,
            volatility=0.01,
            momentum=0.01,
            liquidity=0.7,
        ))
        self.assertEqual(result.metrics["available_fields"], 7)
        self.assertEqual(result.metrics["missing_fields"], ())
        self.assertEqual(result.metrics["invalid_fields"], ())
        self.assertEqual(result.metrics["completeness"], 1.0)

    def test_level1_alpha_score_is_independent_of_risk_and_data_quality(self):
        alpha = (
            AnalyzerResult("price", 0.8, 1.0),
            AnalyzerResult("momentum", 0.6, 0.5),
            AnalyzerResult("volume", 0.4, 1.0),
        )
        risk = (
            AnalyzerResult("volatility", 0.0, 1.0),
            AnalyzerResult("liquidity", 1.0, 1.0),
            AnalyzerResult("data_quality", 0.0, 1.0),
        )
        expected = (0.8 + 0.6 * 0.5 + 0.4) / 2.5
        self.assertAlmostEqual(aggregate(alpha), expected)
        self.assertAlmostEqual(aggregate(alpha + risk), expected)

    def test_level1_exposes_risk_diagnostics_separately(self):
        results = (
            AnalyzerResult("price", 0.7, 1.0),
            AnalyzerResult("momentum", 0.6, 0.0),
            AnalyzerResult("volatility", 0.3, 0.8),
            AnalyzerResult("liquidity", 0.5, 0.9),
            AnalyzerResult("data_quality", 1.0, 1.0),
        )
        self.assertEqual([item.analyzer for item in alpha_results(results)], ["price"])
        self.assertEqual(
            [item.analyzer for item in risk_results(results)],
            ["volatility", "liquidity"],
        )

    def test_level1_without_alpha_evidence_returns_zero_score(self):
        self.assertEqual(aggregate((AnalyzerResult("volatility", 0.9, 1.0),)), 0.0)


if __name__ == "__main__":
    unittest.main()
