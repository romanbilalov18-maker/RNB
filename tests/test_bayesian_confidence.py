import unittest
from types import SimpleNamespace

from bot.intelligence.levels.level_11.analyzers.bayesian_confidence import (
    DEFAULT_MIN_SAMPLES,
    analyze,
    estimate_bayesian_win_rate,
)


class BayesianConfidenceTests(unittest.TestCase):
    def test_uniform_prior_with_no_observations_is_neutral_and_uncertain(self):
        result = estimate_bayesian_win_rate(0, 0)
        self.assertAlmostEqual(result.posterior_mean, 0.5)
        self.assertAlmostEqual(result.posterior_variance, 0.125)
        self.assertEqual(result.credible_interval_95[0], 0.0)
        self.assertEqual(result.credible_interval_95[1], 1.0)
        self.assertFalse(result.ready)
        self.assertEqual(result.evidence_confidence, 0.0)

    def test_posterior_updates_with_wins_and_losses(self):
        result = estimate_bayesian_win_rate(8, 2)
        self.assertAlmostEqual(result.posterior_mean, 8.5 / 11.0)
        self.assertGreater(result.credible_interval_95[0], 0.0)
        self.assertLess(result.credible_interval_95[1], 1.0)
        self.assertGreater(result.evidence_confidence, 0.0)

    def test_all_wins_and_all_losses_do_not_create_zero_or_one_probability(self):
        all_wins = estimate_bayesian_win_rate(20, 0)
        all_losses = estimate_bayesian_win_rate(0, 20)
        self.assertLess(all_wins.posterior_mean, 1.0)
        self.assertGreater(all_losses.posterior_mean, 0.0)

    def test_readiness_depends_on_sample_count(self):
        below = estimate_bayesian_win_rate(DEFAULT_MIN_SAMPLES - 1, 0)
        ready = estimate_bayesian_win_rate(DEFAULT_MIN_SAMPLES, 0)
        self.assertFalse(below.ready)
        self.assertTrue(ready.ready)

    def test_invalid_counts_and_priors_are_rejected(self):
        for args in ((-1, 0), (0, -1), (True, 1), (1.5, 1)):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    estimate_bayesian_win_rate(*args)
        for kwargs in ({"prior_alpha": 0}, {"prior_beta": -1}, {"prior_alpha": float("nan")}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    estimate_bayesian_win_rate(1, 1, **kwargs)

    def test_analyzer_uses_only_matured_three_session_forecasts(self):
        observations = [
            SimpleNamespace(correct=True, outcome_horizon_sessions=3, realized_trade_return=None),
            SimpleNamespace(correct=False, outcome_horizon_sessions=3, realized_trade_return=None),
            SimpleNamespace(correct=True, outcome_horizon_sessions=1, realized_trade_return=None),
            SimpleNamespace(correct=False, outcome_horizon_sessions=5, realized_trade_return=None),
            SimpleNamespace(correct=True, outcome_horizon_sessions=None, realized_trade_return=None),
            SimpleNamespace(correct=True, outcome_horizon_sessions=None, realized_trade_return=0.02),
        ]
        result = analyze(observations, min_samples=2)
        self.assertEqual(result.metrics["sample_count"], 2)
        self.assertEqual(result.metrics["successes"], 1)
        self.assertEqual(result.metrics["failures"], 1)
        self.assertEqual(result.metrics["non_three_session_forecast_observations_excluded"], 3)
        self.assertEqual(result.metrics["closed_trade_observations_excluded"], 1)
        self.assertTrue(result.metrics["ready"])
        self.assertTrue(result.metrics["shadow_only"])
        self.assertFalse(result.metrics["applied_to_trading"])

    def test_insufficient_history_has_zero_confidence_and_warning(self):
        result = analyze([
            SimpleNamespace(correct=True, outcome_horizon_sessions=3, realized_trade_return=None)
        ])
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("bayesian_confidence_insufficient_history", result.warnings)
        self.assertFalse(result.metrics["ready"])


if __name__ == "__main__":
    unittest.main()
