import tempfile
import unittest
from pathlib import Path

from bot.intelligence.levels.level_11.walk_forward_report import build_report
from bot.intelligence.levels.level_11.analyzers.walk_forward_validation import evaluate_walk_forward
from bot.intelligence.levels.level_11.models.learning_observation import LearningObservation


def make_observations(count=60):
    observations = []
    for i in range(count):
        correct = (i % 2 == 0)
        strong = 0.9 if correct else 0.1
        # A weaker feature is wrong on a repeatable subset of observations.
        weak_predicts_correct = correct if i % 4 != 0 else not correct
        weak = 0.8 if weak_predicts_correct else 0.2
        observations.append(
            LearningObservation(
                outcome_return=0.02 if correct else -0.02,
                correct=correct,
                level_scores={"L01": strong, "L02": weak},
                analyzer_scores={"L01:trend": strong, "L02:noise": weak},
            )
        )
    return tuple(observations)


class L11WalkForwardTests(unittest.TestCase):
    def test_insufficient_data_does_not_create_a_validation_claim(self):
        result = evaluate_walk_forward(make_observations(15))
        self.assertEqual(result["status"], "insufficient_data")
        self.assertTrue(result["weights_learned_on_train_only"])

    def test_holdout_is_chronological_and_weights_are_learned_on_train_only(self):
        result = evaluate_walk_forward(make_observations(60), train_fraction=0.6)
        self.assertEqual(result["status"], "evaluated")
        self.assertEqual(result["train_count"], 36)
        self.assertEqual(result["test_count"], 24)
        self.assertTrue(result["weights_learned_on_train_only"])
        self.assertAlmostEqual(sum(result["level_weights"].values()), 1.0)
        self.assertAlmostEqual(sum(result["analyzer_weights"].values()), 1.0)
        self.assertGreater(result["level_weights"]["L01"], result["level_weights"]["L02"])
        self.assertLessEqual(
            result["levels"]["proposed_weighted"]["brier_score"],
            result["levels"]["equal_weight_baseline"]["brier_score"],
        )
        self.assertLessEqual(
            result["analyzers"]["proposed_weighted"]["brier_score"],
            result["analyzers"]["equal_weight_baseline"]["brier_score"],
        )

    def test_report_reads_audit_database_without_enabling_deployment(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = build_report(Path(tmp) / "empty-audit.sqlite")
        self.assertEqual(report["ticker_count"], 0)
        self.assertEqual(report["evaluated_ticker_count"], 0)
        self.assertFalse(report["deployment_allowed"])

    def test_holdout_labels_are_required_for_auc(self):
        result = evaluate_walk_forward(make_observations(60))
        self.assertIsNotNone(result["levels"]["proposed_weighted"]["auc"])
        self.assertIsNotNone(result["levels"]["equal_weight_baseline"]["auc"])


if __name__ == "__main__":
    unittest.main()
