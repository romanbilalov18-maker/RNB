import unittest
from types import SimpleNamespace

from bot.intelligence.pipeline.intelligence_pipeline import _bounded, _overall_consistency


class OverallConsistencyTests(unittest.TestCase):
    def test_bounded_consistency_is_clamped_to_valid_range(self):
        self.assertEqual(_bounded(1.2), 1.0)
        self.assertEqual(_bounded(-0.1), 0.0)

    def test_final_consistency_uses_level10_cross_level_agreement(self):
        self.assertAlmostEqual(_overall_consistency(SimpleNamespace(cross_level_agreement=0.73)), 0.73)

    def test_final_consistency_is_clamped(self):
        self.assertEqual(_overall_consistency(SimpleNamespace(cross_level_agreement=1.4)), 1.0)
        self.assertEqual(_overall_consistency(SimpleNamespace(cross_level_agreement=-0.2)), 0.0)


if __name__ == "__main__":
    unittest.main()
