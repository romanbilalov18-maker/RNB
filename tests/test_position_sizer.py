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


    def test_heuristic_respects_constraints_and_is_compared_with_exact_reference(self):
        analyses = [
            SimpleNamespace(ticker="A", volatility=0.08),
            SimpleNamespace(ticker="B", volatility=0.12),
            SimpleNamespace(ticker="C", volatility=0.20),
        ]
        prices = {"A": 73.0, "B": 121.0, "C": 189.0}
        lot_sizes = {"A": 2, "B": 1, "C": 1}
        cash = 2_000.0
        equity = 5_000.0
        commission_rate = 0.002
        max_weight = 0.35

        exact_sizer = PositionSizer(
            commission_rate=commission_rate,
            max_position_weight=max_weight,
        )
        exact_plans = exact_sizer.plan(
            cash=cash,
            analyses=analyses,
            prices=prices,
            lot_sizes=lot_sizes,
            existing_values={"OLD": 1_000.0},
            total_equity=equity,
        )

        heuristic_sizer = PositionSizer(
            commission_rate=commission_rate,
            max_position_weight=max_weight,
        )
        with patch.object(PositionSizer, "EXACT_SEARCH_LIMIT", 1):
            heuristic_plans = heuristic_sizer.plan(
                cash=cash,
                analyses=analyses,
                prices=prices,
                lot_sizes=lot_sizes,
                existing_values={"OLD": 1_000.0},
                total_equity=equity,
            )

        self.assertTrue(exact_plans)
        self.assertTrue(heuristic_plans)
        self.assertLessEqual(
            sum(plan.total_cost for plan in heuristic_plans),
            cash + 1e-9,
        )
        self.assertLessEqual(
            max(plan.actual_weight for plan in heuristic_plans),
            max_weight + 1e-9,
        )
        self.assertTrue(all(plan.lots >= 1 for plan in heuristic_plans))
        self.assertTrue(all(
            plan.quantity == plan.lots * plan.lot_size
            for plan in heuristic_plans
        ))

        # Compare allocations using the same objective inputs. The heuristic
        # is not required to match the exact optimum, but its result must be
        # feasible and its objective cannot exceed the exact reference.
        tickers = [analysis.ticker for analysis in analyses]
        targets = PositionSizer._target_weights(analyses)
        unit_costs = {
            ticker: prices[ticker] * lot_sizes[ticker] * (1 + commission_rate)
            for ticker in tickers
        }
        existing_values = {"OLD": 1_000.0}
        exact_counts = tuple(
            next((p.lots for p in exact_plans if p.ticker == ticker), 0)
            for ticker in tickers
        )
        heuristic_counts = tuple(
            next((p.lots for p in heuristic_plans if p.ticker == ticker), 0)
            for ticker in tickers
        )
        ranges = [
            range(max(0, int((max_weight * equity - existing_values.get(ticker, 0))
                             / unit_costs[ticker])) + 1)
            for ticker in tickers
        ]
        exact_reference = exact_sizer._exhaustive_best(
            tickers, ranges, unit_costs, existing_values, targets, cash, equity
        )
        heuristic_result = heuristic_sizer._evaluate(
            heuristic_counts, tickers, unit_costs, existing_values, targets,
            cash, equity,
        )
        self.assertIsNotNone(exact_reference)
        self.assertIsNotNone(heuristic_result)
        self.assertLessEqual(
            heuristic_result[0],
            exact_reference[0] + 1e-12,
        )


    def test_heuristic_handles_tight_cash_commission_and_existing_positions(self):
        scenarios = [
            {
                "cash": 250.0,
                "equity": 1_000.0,
                "prices": {"A": 48.0, "B": 79.0, "C": 120.0},
                "lot_sizes": {"A": 1, "B": 1, "C": 1},
                "existing_positions": set(),
                "existing_values": {},
                "commission_rate": 0.01,
                "max_weight": 0.35,
            },
            {
                "cash": 600.0,
                "equity": 2_000.0,
                "prices": {"A": 50.0, "B": 75.0, "C": 110.0},
                "lot_sizes": {"A": 2, "B": 1, "C": 1},
                "existing_positions": {"A"},
                "existing_values": {"A": 500.0},
                "commission_rate": 0.005,
                "max_weight": 0.35,
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                analyses = [
                    SimpleNamespace(ticker="A", volatility=0.08),
                    SimpleNamespace(ticker="B", volatility=0.15),
                    SimpleNamespace(ticker="C", volatility=0.25),
                ]
                sizer = PositionSizer(
                    commission_rate=scenario["commission_rate"],
                    max_position_weight=scenario["max_weight"],
                )
                with patch.object(PositionSizer, "EXACT_SEARCH_LIMIT", 1):
                    plans = sizer.plan(
                        cash=scenario["cash"],
                        analyses=analyses,
                        prices=scenario["prices"],
                        lot_sizes=scenario["lot_sizes"],
                        existing_positions=scenario["existing_positions"],
                        existing_values=scenario["existing_values"],
                        total_equity=scenario["equity"],
                    )

                self.assertLessEqual(
                    sum(plan.total_cost for plan in plans),
                    scenario["cash"] + 1e-9,
                )
                self.assertNotIn(
                    "A" if "A" in scenario["existing_positions"] else "__none__",
                    {plan.ticker for plan in plans},
                )
                self.assertTrue(all(plan.lots >= 1 for plan in plans))
                self.assertTrue(all(
                    plan.quantity == plan.lots * plan.lot_size
                    for plan in plans
                ))
                self.assertTrue(all(
                    plan.actual_weight <= scenario["max_weight"] + 1e-9
                    for plan in plans
                ))


    def test_heuristic_quality_matrix_against_exact_optimizer(self):
        # Small cases are deliberately forced through the heuristic so its
        # allocation quality can be compared with the exhaustive optimum.
        scenarios = [
            {"cash": 500.0, "equity": 1_000.0, "prices": {"A": 17.0, "B": 29.0, "C": 43.0}},
            {"cash": 350.0, "equity": 900.0, "prices": {"A": 23.0, "B": 37.0, "C": 61.0}},
            {"cash": 800.0, "equity": 2_000.0, "prices": {"A": 31.0, "B": 47.0, "C": 73.0}},
        ]
        analyses = [
            SimpleNamespace(ticker="A", volatility=0.07),
            SimpleNamespace(ticker="B", volatility=0.13),
            SimpleNamespace(ticker="C", volatility=0.22),
        ]

        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                kwargs = dict(
                    cash=scenario["cash"],
                    analyses=analyses,
                    prices=scenario["prices"],
                    lot_sizes={"A": 1, "B": 1, "C": 1},
                    existing_values={},
                    total_equity=scenario["equity"],
                )
                exact_sizer = PositionSizer(
                    commission_rate=0.002,
                    max_position_weight=0.35,
                )
                exact_plans = exact_sizer.plan(**kwargs)

                heuristic_sizer = PositionSizer(
                    commission_rate=0.002,
                    max_position_weight=0.35,
                )
                with patch.object(PositionSizer, "EXACT_SEARCH_LIMIT", 1):
                    heuristic_plans = heuristic_sizer.plan(**kwargs)

                self.assertTrue(exact_plans)
                self.assertTrue(heuristic_plans)
                self.assertLessEqual(
                    sum(plan.total_cost for plan in heuristic_plans),
                    scenario["cash"] + 1e-9,
                )
                self.assertTrue(all(
                    plan.actual_weight <= 0.35 + 1e-9
                    for plan in heuristic_plans
                ))

                targets = PositionSizer._target_weights(analyses)
                tickers = [item.ticker for item in analyses]
                unit_costs = {
                    ticker: scenario["prices"][ticker] * 1.002
                    for ticker in tickers
                }
                ranges = [
                    range(int(0.35 * scenario["equity"] / unit_costs[ticker]) + 1)
                    for ticker in tickers
                ]
                exact_reference = exact_sizer._exhaustive_best(
                    tickers, ranges, unit_costs, {}, targets,
                    scenario["cash"], scenario["equity"],
                )
                heuristic_counts = tuple(
                    next((plan.lots for plan in heuristic_plans if plan.ticker == ticker), 0)
                    for ticker in tickers
                )
                heuristic_result = heuristic_sizer._evaluate(
                    heuristic_counts, tickers, unit_costs, {}, targets,
                    scenario["cash"], scenario["equity"],
                )
                self.assertIsNotNone(exact_reference)
                self.assertIsNotNone(heuristic_result)
                # A heuristic may be suboptimal, but these bounded small cases
                # should remain within 10% of the exact objective.
                self.assertGreaterEqual(
                    heuristic_result[0],
                    exact_reference[0] * 0.90,
                )


    def test_rejects_non_finite_cash_and_equity(self):
        analysis = [SimpleNamespace(ticker="A", volatility=0.1)]
        for cash in (float("nan"), float("inf"), -1.0, True):
            with self.subTest(cash=cash):
                with self.assertRaises(ValueError):
                    PositionSizer(commission_rate=0.001).plan(
                        cash=cash,
                        analyses=analysis,
                        prices={"A": 10.0},
                        lot_sizes={"A": 1},
                    )
        with self.assertRaises(ValueError):
            PositionSizer(commission_rate=0.001).plan(
                cash=1000.0,
                analyses=analysis,
                prices={"A": 10.0},
                lot_sizes={"A": 1},
                total_equity=float("nan"),
            )

    def test_rejects_invalid_price_lot_size_and_duplicate_ticker(self):
        sizer = PositionSizer(commission_rate=0.001)
        analysis = [SimpleNamespace(ticker="A", volatility=0.1)]
        invalid_inputs = (
            ({"A": float("nan")}, {"A": 1}),
            ({"A": 0.0}, {"A": 1}),
            ({"A": 10.0}, {"A": 0}),
            ({"A": 10.0}, {"A": True}),
        )
        for prices, lot_sizes in invalid_inputs:
            with self.subTest(prices=prices, lot_sizes=lot_sizes):
                with self.assertRaises(ValueError):
                    sizer.plan(
                        cash=1000.0,
                        analyses=analysis,
                        prices=prices,
                        lot_sizes=lot_sizes,
                    )
        with self.assertRaises(ValueError):
            sizer.plan(
                cash=1000.0,
                analyses=[
                    SimpleNamespace(ticker="A", volatility=0.1),
                    SimpleNamespace(ticker="A", volatility=0.2),
                ],
                prices={"A": 10.0},
                lot_sizes={"A": 1},
            )

if __name__ == "__main__":
    unittest.main()
