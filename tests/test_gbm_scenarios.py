import unittest

from bot.intelligence.levels.level_13.analyzers.gbm_scenarios import simulate_gbm_scenarios


class TestGBMScenarios(unittest.TestCase):
    def test_seeded_simulation_is_reproducible(self):
        first = simulate_gbm_scenarios(100.0, 0.08, 0.20, horizon_steps=30, simulations=300, seed=7)
        second = simulate_gbm_scenarios(100.0, 0.08, 0.20, horizon_steps=30, simulations=300, seed=7)
        self.assertEqual(first, second)

    def test_zero_volatility_produces_deterministic_terminal_price(self):
        result = simulate_gbm_scenarios(100.0, 0.10, 0.0, horizon_steps=10, steps_per_year=10, simulations=50, seed=1)
        self.assertAlmostEqual(result.expected_terminal_price, 100.0 * __import__("math").exp(0.10))
        self.assertAlmostEqual(result.median_terminal_price, result.expected_terminal_price)
        self.assertAlmostEqual(result.percentile_05_terminal_price, result.expected_terminal_price)
        self.assertAlmostEqual(result.percentile_95_terminal_price, result.expected_terminal_price)
        self.assertEqual(result.probability_below_initial_pct, 0.0)
        self.assertIn("zero_volatility_deterministic_paths", result.warnings)

    def test_terminal_quantiles_and_drawdown_are_ordered(self):
        result = simulate_gbm_scenarios(50.0, 0.05, 0.35, horizon_steps=40, simulations=500, seed=11)
        self.assertLessEqual(result.percentile_05_terminal_price, result.median_terminal_price)
        self.assertLessEqual(result.median_terminal_price, result.percentile_95_terminal_price)
        self.assertLessEqual(result.median_max_drawdown_pct, result.percentile_95_max_drawdown_pct)
        self.assertGreaterEqual(result.probability_below_initial_pct, 0.0)
        self.assertLessEqual(result.probability_below_initial_pct, 100.0)

    def test_expected_terminal_price_uses_gbm_arithmetic_expectation(self):
        result = simulate_gbm_scenarios(100.0, 0.12, 0.30, horizon_steps=20, steps_per_year=10, simulations=20, seed=2)
        self.assertAlmostEqual(result.expected_terminal_price, 100.0 * __import__("math").exp(0.24))

    def test_rejects_invalid_parameters(self):
        invalid = [
            ((0.0, 0.1, 0.2), {}),
            ((100.0, 0.1, -0.2), {}),
            ((100.0, float("nan"), 0.2), {}),
            ((100.0, 0.1, 0.2), {"horizon_steps": 0}),
            ((100.0, 0.1, 0.2), {"steps_per_year": 0}),
            ((100.0, 0.1, 0.2), {"simulations": 0}),
            ((100.0, 0.1, 0.2), {"seed": True}),
        ]
        for args, kwargs in invalid:
            with self.subTest(args=args, kwargs=kwargs):
                with self.assertRaises(ValueError):
                    simulate_gbm_scenarios(*args, **kwargs)


if __name__ == "__main__":
    unittest.main()
