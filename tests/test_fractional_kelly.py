import unittest

from bot.portfolio_optimizer.fractional_kelly import calculate_fractional_kelly


class TestFractionalKelly(unittest.TestCase):
    def test_calculates_quarter_kelly_allocation(self):
        result = calculate_fractional_kelly(0.60, 0.02, 0.01, kelly_fraction=0.25)
        self.assertAlmostEqual(result.full_kelly_fraction, 0.40)
        self.assertAlmostEqual(result.recommended_capital_fraction, 0.05)
        self.assertAlmostEqual(result.recommended_capital_pct, 5.0)

    def test_caps_recommended_fraction(self):
        result = calculate_fractional_kelly(
            0.80, 0.03, 0.01, kelly_fraction=0.5, max_capital_fraction=0.04
        )
        self.assertAlmostEqual(result.recommended_capital_fraction, 0.04)

    def test_non_positive_edge_recommends_zero(self):
        result = calculate_fractional_kelly(0.30, 0.01, 0.02)
        self.assertEqual(result.recommended_capital_fraction, 0.0)
        self.assertIn("non_positive_kelly_edge", result.warnings)

    def test_expected_edge_uses_win_and_loss_magnitudes(self):
        result = calculate_fractional_kelly(0.60, 0.02, 0.01)
        self.assertAlmostEqual(result.expected_edge, 0.60 * 0.02 - 0.40 * 0.01)

    def test_zero_and_one_win_probability_are_handled_conservatively(self):
        no_wins = calculate_fractional_kelly(0.0, 0.02, 0.01)
        all_wins = calculate_fractional_kelly(1.0, 0.02, 0.01)
        self.assertEqual(no_wins.recommended_capital_fraction, 0.0)
        self.assertEqual(all_wins.recommended_capital_fraction, 0.0)
        self.assertIn("extreme_win_probability_requires_validation", all_wins.warnings)

    def test_rejects_invalid_parameters(self):
        cases = [
            ((-0.1, 0.02, 0.01), {}),
            ((1.1, 0.02, 0.01), {}),
            ((0.5, 0.0, 0.01), {}),
            ((0.5, 0.02, -0.01), {}),
            ((0.5, 0.02, 0.01), {"kelly_fraction": 0.0}),
            ((0.5, 0.02, 0.01), {"kelly_fraction": 1.1}),
            ((0.5, 0.02, 0.01), {"max_capital_fraction": -0.1}),
            ((0.5, 0.02, 0.01), {"max_capital_fraction": 1.1}),
            ((True, 0.02, 0.01), {}),
        ]
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs):
                with self.assertRaises(ValueError):
                    calculate_fractional_kelly(*args, **kwargs)


if __name__ == "__main__":
    unittest.main()
