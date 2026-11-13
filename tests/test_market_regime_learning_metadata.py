import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.levels.level_03.analyzers.market_regime import (
    _classify_regime,
    analyze as analyze_market_regime,
)
from bot.intelligence.levels.level_03 import level_03_engine


class MarketRegimeLearningMetadataTests(unittest.TestCase):
    def test_regime_requires_directional_consensus(self):
        self.assertEqual(_classify_regime(0.8, 0.7), "bullish")
        self.assertEqual(_classify_regime(0.2, 0.3), "bearish")
        self.assertEqual(_classify_regime(0.5, 0.5), "neutral")
        self.assertEqual(_classify_regime(0.8, 0.2), "mixed")
        self.assertEqual(_classify_regime(0.8, 0.5), "mixed")

    def test_market_regime_analyzer_emits_label_and_method(self):
        level2 = SimpleNamespace(
            analyzer_results=(
                AnalyzerResult("trend", 0.75, 0.9),
                AnalyzerResult("price_structure", 0.70, 0.8),
            )
        )
        result = analyze_market_regime(SimpleNamespace(symbol="AAA"), level2)
        self.assertEqual(result.metrics["regime"], "bullish")
        self.assertEqual(
            result.metrics["regime_method"],
            "directional_consensus_midpoint_v1",
        )
        self.assertGreater(result.confidence, 0.0)

    def test_incomplete_regime_evidence_is_not_fabricated(self):
        level2 = SimpleNamespace(
            analyzer_results=(AnalyzerResult("trend", 0.8, 0.9),)
        )
        result = analyze_market_regime(SimpleNamespace(symbol="AAA"), level2)
        self.assertIsNone(result.metrics["regime"])
        self.assertIn("market_regime_consensus_inputs_incomplete", result.warnings)

    def test_level3_copies_regime_into_metadata_for_l11_snapshot(self):
        regime = AnalyzerResult(
            "market_regime", 0.75, 0.8,
            {
                "regime": "bullish",
                "regime_method": "directional_consensus_midpoint_v1",
                "trend_score": 0.8,
                "structure_score": 0.7,
            },
        )
        other_names = (
            "market_strength", "sector_context", "relative_market",
            "correlation_context", "macro_context",
        )
        fake_modules = [SimpleNamespace(analyze=lambda snapshot, level2, r=regime: r)]
        fake_modules.extend(
            SimpleNamespace(
                analyze=lambda snapshot, level2, n=name: AnalyzerResult(n, 0.5, 0.0)
            )
            for name in other_names
        )
        level2 = SimpleNamespace(
            symbol="AAA", confidence=0.8, consistency=0.7,
            warnings=(), metadata={},
        )
        with patch.object(level_03_engine, "ANALYZERS", tuple(fake_modules)):
            result = level_03_engine.analyze(SimpleNamespace(symbol="AAA"), level2)
        self.assertEqual(result.metadata["regime"], "bullish")
        self.assertEqual(
            result.metadata["regime_method"],
            "directional_consensus_midpoint_v1",
        )
        self.assertEqual(result.metadata["regime_evidence"]["trend_score"], 0.8)


if __name__ == "__main__":
    unittest.main()
