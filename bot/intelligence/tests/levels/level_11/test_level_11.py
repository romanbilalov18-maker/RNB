import unittest

from bot.intelligence.levels.level_11.level_11_engine import Level11Engine
from bot.intelligence.levels.level_11.models.learning_observation import LearningObservation


class TestLevel11(unittest.TestCase):
    def test_runs_without_history(self):
        result = Level11Engine().analyze("TEST")
        self.assertEqual(result.sample_count, 0)
        self.assertEqual(len(result.analyzer_results), 6)
        self.assertTrue(0.0 <= result.score <= 1.0)
        self.assertTrue(result.warnings)

    def test_learns_from_history(self):
        observations = (
            LearningObservation(0.05, True, {"level_01": 0.8, "level_10": 0.9}, {"momentum": 0.85}, "trend"),
            LearningObservation(-0.02, False, {"level_01": 0.3, "level_10": 0.4}, {"momentum": 0.35}, "range"),
            LearningObservation(0.03, True, {"level_01": 0.7, "level_10": 0.8}, {"momentum": 0.75}, "trend"),
        )
        result = Level11Engine().analyze("TEST", observations)
        self.assertEqual(result.sample_count, 3)
        self.assertGreater(result.learning_confidence, 0.0)
        self.assertTrue(0.0 <= result.score <= 1.0)

    def test_does_not_create_trade_decision(self):
        result = Level11Engine().analyze("TEST")
        self.assertFalse(hasattr(result, "buy"))
        self.assertFalse(hasattr(result, "sell"))
        self.assertFalse(hasattr(result, "action"))


if __name__ == "__main__":
    unittest.main()
