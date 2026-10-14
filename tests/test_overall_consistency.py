import unittest
from types import SimpleNamespace

from bot.intelligence.pipeline.intelligence_pipeline import _overall_consistency


class OverallConsistencyTests(unittest.TestCase):
    def test_uses_cross_level_agreement_not_l15_quality_spread(self):
        level10 = SimpleNamespace(cross_level_agreement=0.72)
        self.assertAlmostEqual(_overall_consistency(level10), 0.72)

    def test_clamps_value_to_valid_range(self):
        self.assertEqual(_overall_consistency(SimpleNamespace(cross_level_agreement=1.2)), 1.0)
        self.assertEqual(_overall_consistency(SimpleNamespace(cross_level_agreement=-0.1)), 0.0)


if __name__ == "__main__":
    unittest.main()
