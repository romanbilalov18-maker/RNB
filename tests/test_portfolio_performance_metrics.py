import math
import unittest

from bot.portfolio_analytics.performance_metrics import calculate_performance_metrics


class TestPortfolioPerformanceMetrics(unittest.TestCase):
    def test_calculates_sharpe_sortino_and_drawdown_from_equity_curve(self):
        result = calculate_performance_metrics([100.0, 110.0, 99.0, 108.9], periods_per_year=4)

        self.assertEqual(result.observation_count, 4)
        self.assertEqual(result.return_count, 3)
        self.assertAlmostEqual(result.cumulative_return_pct, 8.9)
        self.assertAlmostEqual(result.max_drawdown_pct, 10.0)
        self.assertIsNotNone(result.sharpe_ratio)
        self.assertIsNotNone(result.sortino_ratio)
        self.assertGreater(result.sortino_ratio, 0.0)
        self.assertGreater(result.annualized_volatility_pct, 0.0)
        self.assertGreater(result.downside_deviation_pct, 0.0)

    def test_risk_free_rate_is_applied_to_sharpe_excess_returns(self):
        zero_rf = calculate_performance_metrics([100, 102, 101], periods_per_year=2)
        positive_rf = calculate_performance_metrics(
            [100, 102, 101], periods_per_year=2, annual_risk_free_rate=0.04
        )
        self.assertLess(positive_rf.sharpe_ratio, zero_rf.sharpe_ratio)

    def test_target_return_changes_sortino_downside_threshold(self):
        zero_target = calculate_performance_metrics([100, 102, 101], periods_per_year=2)
        positive_target = calculate_performance_metrics(
            [100, 102, 101], periods_per_year=2, annual_target_return=0.10
        )
        self.assertNotEqual(zero_target.sortino_ratio, positive_target.sortino_ratio)
        self.assertGreater(positive_target.downside_deviation_pct, zero_target.downside_deviation_pct)

    def test_insufficient_observations_return_unavailable_metrics(self):
        empty = calculate_performance_metrics([])
        single = calculate_performance_metrics([100.0])
        self.assertIsNone(empty.sharpe_ratio)
        self.assertIsNone(empty.sortino_ratio)
        self.assertIsNone(single.cumulative_return_pct)
        self.assertIsNone(single.sharpe_ratio)
        self.assertIn("insufficient_equity_observations", single.warnings)

    def test_zero_volatility_does_not_fabricate_infinite_ratios(self):
        result = calculate_performance_metrics([100.0, 101.0, 102.01], periods_per_year=2)
        self.assertIsNone(result.sharpe_ratio)
        self.assertIsNone(result.sortino_ratio)
        self.assertIn("zero_return_volatility", result.warnings)
        self.assertIn("zero_downside_deviation", result.warnings)

    def test_rejects_invalid_curve_values_and_parameters(self):
        for curve in ([0.0, 1.0], [-1.0, 1.0], [100.0, float("nan")], [100.0, float("inf")], [100.0, True]):
            with self.subTest(curve=curve):
                with self.assertRaises(ValueError):
                    calculate_performance_metrics(curve)
        with self.assertRaises(ValueError):
            calculate_performance_metrics([100, 101], periods_per_year=True)
        with self.assertRaises(ValueError):
            calculate_performance_metrics([100, 101], annual_risk_free_rate=-1.0)

    def test_one_return_can_report_sortino_but_not_sample_sharpe(self):
        result = calculate_performance_metrics([100.0, 90.0], periods_per_year=1)
        self.assertIsNone(result.sharpe_ratio)
        self.assertIsNotNone(result.sortino_ratio)
        self.assertAlmostEqual(result.max_drawdown_pct, 10.0)


if __name__ == "__main__":
    unittest.main()
