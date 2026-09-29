import unittest
from types import SimpleNamespace

from bot.position_sizer import PositionSizer


class TestPositionSizer(unittest.TestCase):
    def test_uses_volatility_and_real_lots(self):
        analyses = [
            SimpleNamespace(ticker="A", volatility=0.10),
            SimpleNamespace(ticker="B", volatility=0.20),
            SimpleNamespace(ticker="C", volatility=0.05),
        ]
        sizer = PositionSizer(commission_rate=0.001)

        plans = sizer.plan(
            cash=10_000,
            analyses=analyses,
            prices={"A": 100, "B": 2000, "C": 50},
            lot_sizes={"A": 10, "B": 1, "C": 100},
        )

        self.assertTrue(plans)
        self.assertTrue(all(plan.lots > 0 for plan in plans))
        self.assertTrue(all(plan.quantity == plan.lots * plan.lot_size for plan in plans))
        self.assertLessEqual(sum(plan.total_cost for plan in plans), 10_000)
        self.assertLessEqual(max(plan.actual_weight for plan in plans), 0.70 + 1e-9)

    def test_never_buys_fractional_lot(self):
        analysis = [SimpleNamespace(ticker="A", volatility=0.10)]
        plan = PositionSizer(commission_rate=0.001).plan(
            cash=1_000,
            analyses=analysis,
            prices={"A": 333},
            lot_sizes={"A": 10},
        )

        self.assertEqual(len(plan), 0)


if __name__ == "__main__":
    unittest.main()
