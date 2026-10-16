import unittest

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result
from bot.intelligence.levels.level_02.analyzers.relative_strength import analyze as analyze_relative_strength
from bot.intelligence.levels.level_02.analyzers.volume_flow import analyze as analyze_volume_flow
from bot.intelligence.levels.level_02.level_02_engine import analyze as analyze_level_02


def level1(*results, confidence=0.8, warnings=()):
    return Level1Result(
        symbol="TEST",
        score=0.5,
        confidence=confidence,
        consistency=0.8,
        analyzer_results=tuple(results),
        warnings=tuple(warnings),
    )


class Level02Level01CompatibilityTests(unittest.TestCase):
    def test_relative_strength_requires_real_relative_market_context(self):
        result = analyze_relative_strength(
            MarketSnapshot(symbol="TEST", price=100, momentum=0.02),
            level1(AnalyzerResult("momentum", 0.9, 1.0)),
        )
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("relative_market_context_unavailable", result.warnings)

    def test_relative_strength_uses_real_relative_return(self):
        result = analyze_relative_strength(
            MarketSnapshot(
                symbol="TEST",
                price=100,
                relative_market_return=0.015,
                relative_market_sample_count=12,
                relative_market_context_available=True,
            ),
            level1(AnalyzerResult("momentum", 0.9, 1.0)),
        )
        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.metrics["relative_market_return"], 0.015)
        self.assertEqual(result.confidence, 1.0)

    def test_volume_flow_uses_real_snapshot_ratio(self):
        result = analyze_volume_flow(
            MarketSnapshot(symbol="TEST", price=101, previous_price=100, volume_ratio=1.5),
            level1(AnalyzerResult("volume", 0.8, 0.9), confidence=0.9),
        )
        self.assertEqual(result.metrics["ratio"], 1.5)
        self.assertEqual(result.metrics["ratio_source"], "volume_ratio")
        self.assertGreater(result.confidence, 0)

    def test_volume_flow_treats_flat_price_as_neutral(self):
        result = analyze_volume_flow(
            MarketSnapshot(symbol="TEST", price=100, previous_price=100, volume_ratio=2.0),
            level1(AnalyzerResult("volume", 0.8, 0.9), confidence=0.9),
        )
        self.assertEqual(result.metrics["confirmation"], 0.5)

    def test_level2_preserves_level1_warnings_and_marks_missing_context(self):
        result = analyze_level_02(
            MarketSnapshot(symbol="TEST", price=100),
            level1(AnalyzerResult("price", 0.7, 0.8), warnings=("level1_input_incomplete",)),
        )
        self.assertIn("level1_input_incomplete", result.warnings)
        self.assertIn("relative_market_context_unavailable", result.warnings)
        self.assertIn("signal_conflict_semantics", result.metadata)

    def test_level2_does_not_claim_confident_result_without_usable_inputs(self):
        result = analyze_level_02(
            MarketSnapshot(symbol="TEST", price=100),
            level1(AnalyzerResult("price", 0.5, 0.0), confidence=0.0),
        )
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("level_02_no_confident_analyzer_results", result.warnings)


if __name__ == "__main__":
    unittest.main()
