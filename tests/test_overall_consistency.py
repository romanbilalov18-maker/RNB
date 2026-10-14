import unittest
from types import SimpleNamespace

from bot.intelligence.pipeline.intelligence_pipeline import (
    _overall_confidence,
    _overall_consistency,
)


class OverallConsistencyTests(unittest.TestCase):
    def test_uses_cross_level_agreement_not_l15_quality_spread(self):
        level10 = SimpleNamespace(cross_level_agreement=0.72)
        self.assertAlmostEqual(_overall_consistency(level10), 0.72)

    def test_clamps_value_to_valid_range(self):
        self.assertEqual(_overall_consistency(SimpleNamespace(cross_level_agreement=1.2)), 1.0)
        self.assertEqual(_overall_consistency(SimpleNamespace(cross_level_agreement=-0.1)), 0.0)

    def test_final_confidence_is_limited_by_agreement_evidence(self):
        level10 = SimpleNamespace(
            confidence=0.9,
            analyzer_results={
                "cross_level_agreement": SimpleNamespace(confidence=0.35)
            },
        )
        level15 = SimpleNamespace(confidence=0.8)
        self.assertAlmostEqual(_overall_confidence(level10, level15), 0.35)

    def test_final_confidence_uses_lower_level15_confidence_when_it_is_lower(self):
        level10 = SimpleNamespace(
            confidence=0.9,
            analyzer_results={
                "cross_level_agreement": SimpleNamespace(confidence=0.7)
            },
        )
        level15 = SimpleNamespace(confidence=0.4)
        self.assertAlmostEqual(_overall_confidence(level10, level15), 0.4)


if __name__ == "__main__":
    unittest.main()
