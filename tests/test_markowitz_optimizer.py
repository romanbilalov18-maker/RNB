import unittest

from bot.portfolio_optimizer.markowitz import optimize_markowitz


class TestMarkowitzOptimizer(unittest.TestCase):
    def test_minimum_variance_prefers_lower_volatility_asset(self):
        returns = {
            "LOW_RISK": [0.001, -0.001, 0.001, -0.001, 0.001, -0.001],
            "HIGH_RISK": [0.03, -0.03, 0.02, -0.02, 0.04, -0.04],
        }
        result = optimize_markowitz(returns, annualization_factor=1)
        self.assertGreater(result.weights["LOW_RISK"], result.weights["HIGH_RISK"])
        self.assertAlmostEqual(sum(result.weights.values()), 1.0)
        self.assertGreaterEqual(result.expected_volatility, 0.0)

    def test_max_weight_cap_is_respected(self):
        returns = {
            "A": [0.01, -0.01, 0.01, -0.01],
            "B": [0.02, -0.02, 0.02, -0.02],
            "C": [-0.01, 0.01, -0.01, 0.01],
        }
        result = optimize_markowitz(returns, max_weight=0.5)
        self.assertTrue(all(weight <= 0.5 + 1e-8 for weight in result.weights.values()))
        self.assertAlmostEqual(sum(result.weights.values()), 1.0)

    def test_mean_variance_objective_accepts_risk_aversion(self):
        returns = {
            "STEADY": [0.005, 0.004, 0.006, 0.005, 0.004],
            "GROWTH": [0.03, -0.02, 0.04, -0.01, 0.03],
        }
        result = optimize_markowitz(
            returns, objective="mean_variance", risk_aversion=2.0, annualization_factor=1
        )
        self.assertEqual(result.objective, "mean_variance")
        self.assertAlmostEqual(sum(result.weights.values()), 1.0)
        self.assertTrue(all(weight >= 0.0 for weight in result.weights.values()))

    def test_target_return_is_reported_as_unmet_when_infeasible(self):
        returns = {"A": [0.001, 0.002, 0.001], "B": [0.0, 0.001, 0.0]}
        result = optimize_markowitz(returns, target_return=0.50, annualization_factor=1)
        self.assertIn("target_return_not_reached", result.warnings)

    def test_rejects_bad_history_and_configuration(self):
        with self.assertRaises(ValueError):
            optimize_markowitz({"A": [0.01]},)
        with self.assertRaises(ValueError):
            optimize_markowitz({"A": [0.01, 0.02], "B": [0.01]})
        with self.assertRaises(ValueError):
            optimize_markowitz({"A": [0.01, 0.02]}, max_weight=0.5)
        with self.assertRaises(ValueError):
            optimize_markowitz({"A": [0.01, 0.02]}, objective="unknown")
        with self.assertRaises(ValueError):
            optimize_markowitz({"A": [0.01, float("nan")]})
        with self.assertRaises(ValueError):
            optimize_markowitz({"A": [0.01, 0.02]}, risk_aversion=0.0)

    def test_one_asset_portfolio_is_fully_invested(self):
        result = optimize_markowitz({"ONLY": [0.01, -0.01, 0.02]}, max_weight=1.0)
        self.assertEqual(result.weights, {"ONLY": 1.0})
        self.assertAlmostEqual(sum(result.weights.values()), 1.0)


if __name__ == "__main__":
    unittest.main()
