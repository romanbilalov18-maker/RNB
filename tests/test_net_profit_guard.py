import unittest

from bot.net_profit_guard import assess_net_profit
from bot.paper_executor import PaperExecutor


class NetProfitGuardTests(unittest.TestCase):
    def test_net_return_passes_after_costs(self):
        result = assess_net_profit(
            expected_gross_return=.02,
            commission_rate=.0005,
            spread_pct=.002,
            slippage_bps=5,
            minimum_net_return=.01,
        )
        # Commission = .0005 entry + .00051 exit; spread .002;
        # round-trip slippage .001.
        self.assertTrue(result.allowed)
        self.assertAlmostEqual(result.round_trip_commission, .00101)
        self.assertAlmostEqual(result.expected_net_return, .01599)

    def test_exit_commission_scales_with_expected_exit_notional(self):
        result = assess_net_profit(
            expected_gross_return=.10,
            commission_rate=.01,
            spread_pct=0.0,
            slippage_bps=0.0,
        )
        # Entry fee 1% + exit fee 1% of 110% notional = 2.1%.
        self.assertAlmostEqual(result.round_trip_commission, .021)
        self.assertAlmostEqual(result.expected_net_return, .079)

    def test_costs_block_profitable_gross_signal(self):
        result = assess_net_profit(
            expected_gross_return=.003,
            commission_rate=.001,
            spread_pct=.002,
            slippage_bps=10,
            minimum_net_return=0,
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "net_return_below_threshold")

    def test_minimum_take_profit_can_be_erased_by_round_trip_costs(self):
        result = assess_net_profit(
            expected_gross_return=.0025,
            commission_rate=.0005,
            spread_pct=.001,
            slippage_bps=5,
            minimum_net_return=0,
        )
        self.assertFalse(result.allowed)
        self.assertLess(result.expected_net_return, 0)

    def test_zero_costs_preserve_gross_return(self):
        result = assess_net_profit(
            expected_gross_return=.025,
            commission_rate=0.0,
            spread_pct=0.0,
            slippage_bps=0.0,
        )
        self.assertTrue(result.allowed)
        self.assertEqual(result.expected_net_return, .025)

    def test_paper_executor_accepts_and_stores_minimum_net_return(self):
        executor = PaperExecutor(minimum_net_return=0.0005)
        self.assertEqual(executor.minimum_net_return, 0.0005)

    def test_paper_executor_rejects_invalid_minimum_net_return(self):
        for value in (-0.001, 1.1, float("nan"), True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    PaperExecutor(minimum_net_return=value)

    def test_invalid_inputs_fail_closed(self):
        cases = [
            ("expected_gross_return", float("nan")),
            ("commission_rate", -.1),
            ("commission_rate", 1.0),
            ("spread_pct", 1.1),
            ("slippage_bps", -1),
            ("minimum_net_return", True),
        ]
        defaults = dict(
            expected_gross_return=.01,
            commission_rate=.001,
            spread_pct=.001,
            slippage_bps=5,
            minimum_net_return=0,
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                args = defaults.copy()
                args[field] = value
                with self.assertRaises(ValueError):
                    assess_net_profit(**args)


if __name__ == "__main__":
    unittest.main()
