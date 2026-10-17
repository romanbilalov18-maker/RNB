import math
import unittest

from bot.intelligence.levels.level_11.level_11_engine import Level11Engine
from bot.intelligence.levels.level_11.models.learning_observation import LearningObservation


class TestLearningObservationValidation(unittest.TestCase):
    def test_accepts_valid_observation(self):
        item = LearningObservation(
            0.025, True, {"level_10": 0.8}, {"momentum": 0.75}, "trend",
            "2026-10-01T12:00:00+03:00", "2026-10-06",
        )
        self.assertEqual(item.outcome_return, 0.025)

    def test_rejects_non_finite_outcome_return(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                LearningObservation(value, True)

    def test_rejects_boolean_outcome_return(self):
        with self.assertRaises(ValueError):
            LearningObservation(True, True)

    def test_rejects_non_boolean_correctness(self):
        for value in (1, 0, "false", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                LearningObservation(0.01, value)

    def test_rejects_non_finite_or_invalid_feature_scores(self):
        for value in (math.nan, math.inf, -math.inf, -0.01, 1.01, True, "0.5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                LearningObservation(0.01, True, {"level_10": value})

    def test_rejects_invalid_mapping_and_keys(self):
        with self.assertRaises(ValueError):
            LearningObservation(0.01, True, ["level_10"])
        with self.assertRaises(ValueError):
            LearningObservation(0.01, True, {" ": 0.5})

    def test_rejects_empty_optional_metadata(self):
        with self.assertRaises(ValueError):
            LearningObservation(0.01, True, regime=" ")

    def test_normal_learning_path_remains_available(self):
        observations = (
            LearningObservation(0.05, True, {"level_01": 0.8, "level_10": 0.9}, {"momentum": 0.85}, "trend"),
            LearningObservation(-0.02, False, {"level_01": 0.3, "level_10": 0.4}, {"momentum": 0.35}, "range"),
            LearningObservation(0.03, True, {"level_01": 0.7, "level_10": 0.8}, {"momentum": 0.75}, "trend"),
        )
        result = Level11Engine().analyze("TEST", observations)
        self.assertEqual(result.sample_count, 3)
        self.assertGreater(result.learning_confidence, 0.0)
        self.assertTrue(0.0 <= result.score <= 1.0)


if __name__ == "__main__":
    unittest.main()
