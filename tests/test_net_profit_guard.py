import unittest

from bot.net_profit_guard import assess_net_profit


class NetProfitGuardTests(unittest.TestCase):
    def test_net_return_passes_after_costs(self):
        result = assess_net_profit(
            expected_gross_return=.02,
            commission_rate=.0005,
            spread_pct=.002,
            slippage_bps=5,
            minimum_net_return=.01,
        )
        # Round-trip commission .001 + full spread .002 + round-trip slippage .001
        self.assertTrue(result.allowed)
        self.assertAlmostEqual(result.expected_net_return, .016)

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

    def test_invalid_inputs_fail_closed(self):
        cases = [
            ("expected_gross_return", float("nan")),
            ("commission_rate", -.1),
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
