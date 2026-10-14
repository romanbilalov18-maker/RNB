import tempfile
import unittest
from datetime import date, timedelta
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

    def test_weighted_prediction_renormalizes_when_features_are_missing(self):
        from bot.intelligence.levels.level_11.analyzers.walk_forward_validation import _weighted_prediction

        weights = {"L01": 0.7, "L02": 0.3}
        self.assertAlmostEqual(_weighted_prediction({"L01": 0.8}, weights), 0.8)
        self.assertAlmostEqual(_weighted_prediction({"L02": 0.2}, weights), 0.2)
        self.assertAlmostEqual(_weighted_prediction({}, weights), 0.5)
        self.assertAlmostEqual(_weighted_prediction({"L01": 0.8, "L02": 0.2}, weights), 0.62)

    def test_purges_training_labels_that_mature_in_holdout_period(self):
        rows = []
        first_day = date(2026, 1, 1)
        for i in range(60):
            decision_day = first_day + timedelta(days=i)
            target_day = date(2026, 2, 8) if i == 34 else decision_day + timedelta(days=3)
            rows.append(LearningObservation(
                outcome_return=0.01, correct=(i % 2 == 0),
                level_scores={"L01": 0.8 if i % 2 == 0 else 0.2},
                analyzer_scores={"trend": 0.8 if i % 2 == 0 else 0.2},
                decision_time=f"{decision_day.isoformat()}T12:00:00+00:00",
                outcome_target_date=target_day.isoformat(),
            ))
        result = evaluate_walk_forward(rows, train_fraction=0.6)
        self.assertEqual(result["status"], "evaluated")
        self.assertEqual(result["raw_train_count"], 36)
        self.assertEqual(result["purged_train_count"], 3)
        self.assertEqual(result["train_count"], 33)
        self.assertTrue(result["purging_applied"])

    def test_multiple_windows_use_disjoint_chronological_holdouts(self):
        rows = []
        first_day = date(2026, 1, 1)
        for i in range(90):
            decision_day = first_day + timedelta(days=i)
            correct = i % 2 == 0
            rows.append(LearningObservation(
                outcome_return=0.02 if correct else -0.02,
                correct=correct,
                level_scores={"L01": 0.9 if correct else 0.1, "L02": 0.2 if correct else 0.8},
                analyzer_scores={"trend": 0.9 if correct else 0.1, "noise": 0.2 if correct else 0.8},
                decision_time=f"{decision_day.isoformat()}T12:00:00+00:00",
                outcome_target_date=(decision_day + timedelta(days=3)).isoformat(),
            ))
        from bot.intelligence.levels.level_11.analyzers.walk_forward_validation import evaluate_multiple_windows
        result = evaluate_multiple_windows(rows, window_count=3, min_test_size=10)
        self.assertEqual(result["status"], "evaluated")
        self.assertEqual(result["evaluated_windows"], 3)
        self.assertFalse(result["deployment_allowed"])
        ranges = [(window["test_start_index"], window["test_end_index"]) for window in result["windows"]]
        self.assertTrue(all(left[1] <= right[0] for left, right in zip(ranges, ranges[1:])))
        self.assertIn("delta", result["summary"]["levels"])

    def test_multiple_windows_refuse_insufficient_history(self):
        from bot.intelligence.levels.level_11.analyzers.walk_forward_validation import evaluate_multiple_windows
        result = evaluate_multiple_windows(make_observations(25), window_count=3, min_test_size=10)
        self.assertEqual(result["status"], "insufficient_data")
        self.assertFalse(result["deployment_allowed"])

    def test_holdout_labels_are_required_for_auc(self):
        result = evaluate_walk_forward(make_observations(60))
        self.assertIsNotNone(result["levels"]["proposed_weighted"]["auc"])
        self.assertIsNotNone(result["levels"]["equal_weight_baseline"]["auc"])


if __name__ == "__main__":
    unittest.main()
