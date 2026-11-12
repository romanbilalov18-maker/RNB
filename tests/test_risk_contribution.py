import unittest

from bot.portfolio_analytics.risk_contribution import calculate_euler_risk_contribution


class TestEulerRiskContribution(unittest.TestCase):
    def test_component_contributions_sum_to_portfolio_volatility(self):
        returns = {
            "A": [0.01, -0.02, 0.03, -0.01, 0.02],
            "B": [-0.01, 0.02, -0.02, 0.03, -0.01],
        }
        result = calculate_euler_risk_contribution(returns, {"A": 0.6, "B": 0.4})

        self.assertEqual(result.observation_count, 5)
        self.assertGreater(result.portfolio_volatility, 0.0)
        self.assertAlmostEqual(result.contribution_sum_pct, 100.0)
        self.assertAlmostEqual(
            sum(item.component_risk for item in result.assets),
            result.portfolio_volatility,
        )

    def test_weights_are_normalized_and_asset_contributions_are_reported(self):
        result = calculate_euler_risk_contribution(
            {"AAA": [0.01, -0.01, 0.02], "BBB": [0.02, -0.02, 0.01]},
            {"AAA": 60, "BBB": 40},
        )
        self.assertEqual([item.asset for item in result.assets], ["AAA", "BBB"])
        self.assertAlmostEqual(sum(item.weight_pct for item in result.assets), 100.0)
        self.assertTrue(all(item.marginal_risk is not None for item in result.assets))

    def test_zero_volatility_returns_unavailable_contribution_percentages(self):
        result = calculate_euler_risk_contribution(
            {"AAA": [0.0, 0.0, 0.0], "BBB": [0.0, 0.0, 0.0]},
            {"AAA": 0.5, "BBB": 0.5},
        )
        self.assertEqual(result.portfolio_volatility, 0.0)
        self.assertIsNone(result.contribution_sum_pct)
        self.assertTrue(all(item.contribution_pct is None for item in result.assets))
        self.assertIn("zero_portfolio_volatility", result.warnings)

    def test_insufficient_history_returns_unavailable_result(self):
        result = calculate_euler_risk_contribution({"AAA": [0.01]}, {"AAA": 1.0})
        self.assertIsNone(result.portfolio_volatility)
        self.assertEqual(result.assets, ())
        self.assertIn("insufficient_aligned_return_history", result.warnings)

    def test_rejects_misaligned_series_and_weight_keys(self):
        with self.assertRaises(ValueError):
            calculate_euler_risk_contribution(
                {"AAA": [0.01, 0.02], "BBB": [0.01]}, {"AAA": 0.5, "BBB": 0.5}
            )
        with self.assertRaises(ValueError):
            calculate_euler_risk_contribution({"AAA": [0.01, 0.02]}, {"BBB": 1.0})

    def test_rejects_invalid_returns_and_weights(self):
        for values in ([0.1, -1.0], [0.1, float("nan")], [0.1, float("inf")], [0.1, True]):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    calculate_euler_risk_contribution({"AAA": values}, {"AAA": 1.0})
        for weight in (-0.1, float("nan"), float("inf"), True):
            with self.subTest(weight=weight):
                with self.assertRaises(ValueError):
                    calculate_euler_risk_contribution({"AAA": [0.01, 0.02]}, {"AAA": weight})
        with self.assertRaises(ValueError):
            calculate_euler_risk_contribution({"AAA": [0.01, 0.02]}, {"AAA": 0.0})


if __name__ == "__main__":
    unittest.main()
