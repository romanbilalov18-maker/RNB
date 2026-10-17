import unittest
from datetime import datetime, timedelta, timezone

from bot.intelligence.levels.level_11.models.learning_observation import LearningObservation
from bot.intelligence.levels.level_11.validation import evaluate_feature_group


class TestL11ChronologicalValidation(unittest.TestCase):
    @staticmethod
    def observation(day, target_day, correct=True):
        decision = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)
        target = (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=target_day)).date().isoformat()
        return LearningObservation(
            0.01 if correct else -0.01,
            correct,
            {"L01": 0.8 if correct else 0.2, "L02": 0.7},
            {"L01:signal": 0.75 if correct else 0.25},
            "trend",
            decision.isoformat(),
            target,
        )

    def test_rejects_missing_timestamps_instead_of_using_input_order(self):
        rows = tuple(
            LearningObservation(0.01, True, {"L01": 0.8}, {"signal": 0.7})
            for _ in range(30)
        )
        report = evaluate_feature_group(rows, "level_scores")
        self.assertEqual(report["status"], "insufficient_history")
        self.assertFalse(report["chronology_verified"])
        self.assertIn("timestamps are missing", report["reason"])

    def test_rejects_duplicate_timestamps(self):
        row = self.observation(1, 2)
        report = evaluate_feature_group((row, row), "level_scores")
        self.assertIn("duplicate", report["reason"])

    def test_purges_training_labels_that_reach_holdout_boundary(self):
        rows = []
        for i in range(40):
            # First 28 observations train; boundary is day 28.
            # The final three training labels mature on/after the boundary.
            target_day = i + 1 if i < 25 else 30
            rows.append(self.observation(i, target_day, correct=i % 2 == 0))
        report = evaluate_feature_group(
            tuple(reversed(rows)), "level_scores",
            train_fraction=0.7, min_train_samples=1, min_test_samples=1,
        )
        self.assertTrue(report["chronology_verified"])
        self.assertEqual(report["raw_train_samples"], 28)
        self.assertGreater(report["purged_train_samples"], 0)
        self.assertEqual(report["train_samples"] + report["purged_train_samples"], 28)
        self.assertFalse(report["weights_applied_to_trading"])

    def test_malformed_target_dates_are_purged_not_used_for_training(self):
        rows = [self.observation(i, i + 1) for i in range(30)]
        rows[0] = LearningObservation(
            0.01, True, {"L01": 0.8}, {"signal": 0.7}, "trend",
            rows[0].decision_time, "not-a-date",
        )
        report = evaluate_feature_group(
            tuple(rows), "level_scores", train_fraction=0.7,
            min_train_samples=1, min_test_samples=1,
        )
        self.assertGreater(report["purged_train_samples"], 0)
        self.assertFalse(report["weights_applied_to_trading"])


    def test_purging_uses_moscow_market_date_not_utc_date(self):
        # 21:30 UTC is already the next calendar date in Moscow.
        boundary = datetime(2026, 1, 10, 21, 30, tzinfo=timezone.utc)
        train = (
            LearningObservation(
                0.01, True, {"L01": 0.8}, {"signal": 0.7}, "trend",
                (boundary - timedelta(days=1)).isoformat(), "2026-01-10",
            ),
        )
        test = (
            LearningObservation(
                0.01, True, {"L01": 0.8}, {"signal": 0.7}, "trend",
                boundary.isoformat(), "2026-01-12",
            ),
        )
        from bot.intelligence.levels.level_11.validation import _purge_overlapping_labels
        kept, purged, error = _purge_overlapping_labels(train, test)
        self.assertIsNone(error)
        self.assertEqual(kept, ())
        self.assertEqual(purged, 1)


if __name__ == "__main__":
    unittest.main()
