import unittest

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result
from bot.intelligence.levels.level_02.analyzers.price_structure import analyze as analyze_price_structure
from bot.intelligence.levels.level_02.analyzers.signal_conflict import analyze as analyze_signal_conflict


def make_level1(*results, confidence=0.8):
    return Level1Result("TEST", 0.5, confidence, 0.8, tuple(results))


class Level02PriceAndConsistencyTests(unittest.TestCase):
    def test_price_structure_requires_level1_price_evidence(self):
        result = analyze_price_structure(
            MarketSnapshot(symbol="TEST", price=101, previous_price=100),
            make_level1(AnalyzerResult("price", 0.5, 0.0)),
        )
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("price_structure_inputs_unavailable", result.warnings)

    def test_price_structure_combines_price_score_and_observed_direction(self):
        result = analyze_price_structure(
            MarketSnapshot(symbol="TEST", price=101, previous_price=100),
            make_level1(AnalyzerResult("price", 0.6, 0.9)),
        )
        self.assertAlmostEqual(result.score, 0.7 * 0.6 + 0.3)
        self.assertAlmostEqual(result.confidence, 0.8)

    def test_signal_conflict_does_not_claim_directional_conflict(self):
        result = analyze_signal_conflict(
            MarketSnapshot(symbol="TEST", price=100),
            make_level1(AnalyzerResult("price", 0.9, 0.8), AnalyzerResult("momentum", 0.2, 0.8)),
        )
        self.assertFalse(result.metrics["directional_conflict_assessed"])
        self.assertAlmostEqual(result.metrics["score_dispersion"], 0.7)
        self.assertIn("directional_conflict_not_assessed_score_dispersion_only", result.warnings)

    def test_signal_conflict_has_zero_confidence_without_level1_evidence(self):
        result = analyze_signal_conflict(
            MarketSnapshot(symbol="TEST", price=100),
            make_level1(AnalyzerResult("price", 0.9, 0.0)),
            confidence=0.0,
        )
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("no_observed_analyzer_results", result.warnings)


if __name__ == "__main__":
    unittest.main()
