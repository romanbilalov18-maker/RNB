import unittest
from types import SimpleNamespace
from unittest.mock import patch

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

    def test_respects_existing_position_concentration(self):
        analyses = [
            SimpleNamespace(ticker="A", volatility=0.10),
            SimpleNamespace(ticker="B", volatility=0.10),
        ]
        plans = PositionSizer(commission_rate=0.0, max_position_weight=0.35).plan(
            cash=7_000,
            analyses=analyses,
            prices={"A": 100, "B": 100},
            lot_sizes={"A": 10, "B": 10},
            existing_positions={"A"},
            existing_values={"A": 3_500},
            total_equity=10_000,
        )

        self.assertTrue(plans)
        self.assertEqual({plan.ticker for plan in plans}, {"B"})
        self.assertLessEqual(max(plan.actual_weight for plan in plans), 0.35 + 1e-9)

    def test_does_not_buy_held_ticker(self):
        analyses = [
            SimpleNamespace(ticker="A", volatility=0.10),
            SimpleNamespace(ticker="B", volatility=0.10),
        ]
        plans = PositionSizer(commission_rate=0.0).plan(
            cash=10_000,
            analyses=analyses,
            prices={"A": 100, "B": 100},
            lot_sizes={"A": 10, "B": 10},
            existing_positions={"A"},
            existing_values={"A": 1_000},
            total_equity=10_000,
        )
        self.assertNotIn("A", {plan.ticker for plan in plans})

    def test_never_buys_fractional_lot(self):
        analysis = [SimpleNamespace(ticker="A", volatility=0.10)]
        plan = PositionSizer(commission_rate=0.001).plan(
            cash=1_000,
            analyses=analysis,
            prices={"A": 333},
            lot_sizes={"A": 10},
        )
        self.assertEqual(len(plan), 0)

    def test_large_search_uses_bounded_heuristic_and_respects_constraints(self):
        analyses = [
            SimpleNamespace(ticker=f"T{i}", volatility=0.01 + i * 0.001)
            for i in range(10)
        ]
        prices = {analysis.ticker: 100.0 for analysis in analyses}
        lot_sizes = {analysis.ticker: 1 for analysis in analyses}
        sizer = PositionSizer(commission_rate=0.001, max_position_weight=0.35)

        # Force the bounded path deterministically instead of relying on a
        # timing-sensitive test or a machine-dependent combination count.
        with patch.object(PositionSizer, "EXACT_SEARCH_LIMIT", 1):
            plans = sizer.plan(
                cash=10_000,
                analyses=analyses,
                prices=prices,
                lot_sizes=lot_sizes,
            )

        self.assertTrue(plans)
        self.assertLessEqual(sum(plan.total_cost for plan in plans), 10_000 + 1e-9)
        self.assertTrue(all(plan.lots >= 1 for plan in plans))
        self.assertTrue(all(plan.quantity == plan.lots * plan.lot_size for plan in plans))
        self.assertLessEqual(max(plan.actual_weight for plan in plans), 0.35 + 1e-9)

    def test_small_search_stays_on_exact_path(self):
        analyses = [
            SimpleNamespace(ticker="A", volatility=0.1),
            SimpleNamespace(ticker="B", volatility=0.2),
        ]
        sizer = PositionSizer(commission_rate=0.001)
        with patch.object(sizer, "_exhaustive_best", wraps=sizer._exhaustive_best) as exact:
            sizer.plan(
                cash=1_000,
                analyses=analyses,
                prices={"A": 100, "B": 150},
                lot_sizes={"A": 1, "B": 1},
            )
        exact.assert_called_once()


if __name__ == "__main__":
    unittest.main()
