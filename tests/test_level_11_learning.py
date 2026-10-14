import unittest

from bot.intelligence.levels.level_11.level_11_engine import Level11Engine
from bot.intelligence.levels.level_11.models.learning_observation import LearningObservation


class Level11LearningTests(unittest.TestCase):
    def test_empty_history_is_explicitly_untrained(self):
        result = Level11Engine().analyze("AAA")
        self.assertEqual(result.sample_count, 0)
        self.assertEqual(result.learning_confidence, 0.0)
        self.assertIn("learning_history_not_available", result.warnings)

    def test_matured_observations_feed_learning_analyzers(self):
        observations = (
            LearningObservation(
                outcome_return=0.04,
                correct=True,
                level_scores={"L01": 0.8, "L06": 0.7},
                analyzer_scores={"L01:trend": 0.9, "L06:risk": 0.6},
                regime="bullish",
            ),
            LearningObservation(
                outcome_return=-0.02,
                correct=False,
                level_scores={"L01": 0.4, "L06": 0.5},
                analyzer_scores={"L01:trend": 0.3, "L06:risk": 0.7},
                regime="bearish",
            ),
        )
        result = Level11Engine().analyze("AAA", observations)
        self.assertEqual(result.sample_count, 2)
        self.assertAlmostEqual(result.outcome_quality, 0.5)
        self.assertGreater(result.learning_confidence, 0.0)
        self.assertEqual(result.metadata["adaptive_weights_are_proposals"], True)

    def test_learning_score_uses_normalized_weights(self):
        observations = (
            LearningObservation(
                outcome_return=0.01,
                correct=True,
                level_scores={"L01": 0.8, "L02": 0.6},
                analyzer_scores={"trend": 0.7},
                regime="bullish",
            ),
        )
        engine = Level11Engine()
        result = engine.analyze("AAA", observations)
        expected = sum(
            item.score * weight
            for item, weight in zip(result.analyzer_results, engine.WEIGHTS)
        ) / sum(engine.WEIGHTS)
        self.assertAlmostEqual(result.score, expected)


if __name__ == "__main__":
    unittest.main()
