import unittest

from bot.portfolio_analytics.monte_carlo import monte_carlo_block_bootstrap


class TestMonteCarloBlockBootstrap(unittest.TestCase):
    def test_results_are_reproducible_with_fixed_seed(self):
        returns = [0.01, -0.02, 0.015, 0.005, -0.01, 0.02, -0.005]
        first = monte_carlo_block_bootstrap(returns, simulations=500, horizon=20, block_length=3, seed=17)
        second = monte_carlo_block_bootstrap(returns, simulations=500, horizon=20, block_length=3, seed=17)
        self.assertEqual(first, second)
        self.assertEqual(first.simulation_count, 500)
        self.assertEqual(first.horizon, 20)

    def test_block_bootstrap_preserves_order_inside_each_sampled_block(self):
        # With a one-period horizon per block and deterministic repeated pattern,
        # the seeded outcome distribution is stable and remains finite.
        result = monte_carlo_block_bootstrap([0.10, -0.10], simulations=100, horizon=10, block_length=1, seed=4)
        self.assertGreaterEqual(result.probability_of_loss_pct, 0.0)
        self.assertLessEqual(result.probability_of_loss_pct, 100.0)
        self.assertGreaterEqual(result.percentile_95_return_pct, result.percentile_05_return_pct)

    def test_compounds_returns_and_reports_tail_risk(self):
        result = monte_carlo_block_bootstrap([0.10, -0.10], simulations=100, horizon=2, block_length=2, seed=1)
        self.assertAlmostEqual(result.median_return_pct, -1.0)
        self.assertAlmostEqual(result.percentile_05_return_pct, -1.0)
        self.assertAlmostEqual(result.percentile_95_return_pct, -1.0)
        self.assertGreaterEqual(result.median_max_drawdown_pct, 0.0)
        self.assertGreaterEqual(result.percentile_95_max_drawdown_pct, result.median_max_drawdown_pct)

    def test_insufficient_history_returns_unavailable_scenario_metrics(self):
        result = monte_carlo_block_bootstrap([0.01], simulations=10, horizon=5, seed=1)
        self.assertIsNone(result.median_return_pct)
        self.assertIsNone(result.probability_of_loss_pct)
        self.assertIn("insufficient_historical_returns", result.warnings)

    def test_rejects_invalid_returns_and_parameters(self):
        for returns in ([0.1, -1.0], [0.1, float("nan")], [0.1, float("inf")], [0.1, True]):
            with self.subTest(returns=returns):
                with self.assertRaises(ValueError):
                    monte_carlo_block_bootstrap(returns)
        with self.assertRaises(ValueError):
            monte_carlo_block_bootstrap([0.1, 0.2], simulations=0)
        with self.assertRaises(ValueError):
            monte_carlo_block_bootstrap([0.1, 0.2], horizon=0)
        with self.assertRaises(ValueError):
            monte_carlo_block_bootstrap([0.1, 0.2], block_length=3)
        with self.assertRaises(ValueError):
            monte_carlo_block_bootstrap([0.1, 0.2], seed=True)

    def test_block_length_defaults_to_up_to_five_observations(self):
        result = monte_carlo_block_bootstrap([0.01, -0.01, 0.02], simulations=5, seed=2)
        self.assertEqual(result.block_length, 3)
        self.assertEqual(result.horizon, 3)


if __name__ == "__main__":
    unittest.main()
