import unittest
from types import SimpleNamespace

from bot.intelligence.pipeline.intelligence_pipeline import _bounded


class OverallConsistencyTests(unittest.TestCase):
    def test_bounded_consistency_is_clamped_to_valid_range(self):
        self.assertEqual(_bounded(1.2), 1.0)
        self.assertEqual(_bounded(-0.1), 0.0)


if __name__ == "__main__":
    unittest.main()
