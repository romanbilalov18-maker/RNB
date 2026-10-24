import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bot.paper_executor import PaperExecutor


class PaperExecutorIntelligenceGateTests(unittest.TestCase):
    def setUp(self):
        self.allowed = SimpleNamespace(
            ticker="AAA", volatility=0.02, momentum=0.03, trend_strength=1.0
        )
        self.blocked = SimpleNamespace(
            ticker="BBB", volatility=0.03, momentum=0.02, trend_strength=1.0
        )
        self.scan = SimpleNamespace(
            analyses={"AAA": self.allowed, "BBB": self.blocked},
            buy_candidates=[self.allowed, self.blocked],
            current_prices={"AAA": 10.0, "BBB": 20.0},
            lot_sizes={"AAA": 1, "BBB": 1},
        )
        self.portfolio = SimpleNamespace(
            positions={},
            trades=[],
            cash=1000.0,
            commission_rate=0.001,
            equity=lambda prices: 1000.0,
        )

    def test_only_intelligence_approved_tickers_reach_position_sizer(self):
        with patch("bot.paper_executor.PositionManager") as manager_cls, patch(
            "bot.paper_executor.PositionSizer"
        ) as sizer_cls:
            manager = manager_cls.return_value
            manager.evaluate.return_value = []
            manager.execute_sales.return_value = []
            sizer_cls.return_value.plan.return_value = []

            PaperExecutor().execute(
                self.portfolio, self.scan, eligible_buy_tickers={"AAA"}
            )

            eligible = sizer_cls.return_value.plan.call_args.kwargs["analyses"]
            self.assertEqual([item.ticker for item in eligible], ["AAA"])

    def test_empty_intelligence_allowlist_blocks_all_new_buys(self):
        with patch("bot.paper_executor.PositionManager") as manager_cls, patch(
            "bot.paper_executor.PositionSizer"
        ) as sizer_cls:
            manager = manager_cls.return_value
            manager.evaluate.return_value = []
            manager.execute_sales.return_value = []
            sizer_cls.return_value.plan.return_value = []

            PaperExecutor().execute(
                self.portfolio, self.scan, eligible_buy_tickers=set()
            )

            eligible = sizer_cls.return_value.plan.call_args.kwargs["analyses"]
            self.assertEqual(eligible, [])

    def test_fallback_considers_only_approved_fresh_active_tickers_outside_ranked_list(self):
        fallback = SimpleNamespace(
            ticker="CCC", volatility=0.01, momentum=0.04, trend_strength=1.0,
            score=0.9,
        )
        self.scan.analyses["CCC"] = fallback
        self.scan.current_prices["CCC"] = 5.0
        self.scan.lot_sizes["CCC"] = 1
        self.scan.fresh_quote_tickers = {"AAA", "BBB", "CCC"}
        self.scan.active_trading_tickers = {"AAA", "BBB", "CCC"}

        with patch("bot.paper_executor.PositionManager") as manager_cls, patch(
            "bot.paper_executor.PositionSizer"
        ) as sizer_cls:
            manager = manager_cls.return_value
            manager.evaluate.return_value = []
            manager.execute_sales.return_value = []
            sizer_cls.return_value.plan.return_value = []

            PaperExecutor().execute(
                self.portfolio, self.scan,
                eligible_buy_tickers={"AAA", "BBB", "CCC"},
            )

            calls = sizer_cls.return_value.plan.call_args_list
            self.assertEqual(len(calls), 2)
            first = [item.ticker for item in calls[0].kwargs["analyses"]]
            second = [item.ticker for item in calls[1].kwargs["analyses"]]
            self.assertEqual(first, ["AAA", "BBB"])
            self.assertIn("CCC", second)

    def test_fallback_does_not_consider_unapproved_or_stale_tickers(self):
        fallback = SimpleNamespace(
            ticker="CCC", volatility=0.01, momentum=0.04, trend_strength=1.0,
            score=0.9,
        )
        stale = SimpleNamespace(
            ticker="DDD", volatility=0.01, momentum=0.05, trend_strength=1.0,
            score=0.95,
        )
        self.scan.analyses.update({"CCC": fallback, "DDD": stale})
        self.scan.current_prices.update({"CCC": 5.0, "DDD": 4.0})
        self.scan.lot_sizes.update({"CCC": 1, "DDD": 1})
        self.scan.fresh_quote_tickers = {"AAA", "BBB", "CCC"}
        self.scan.active_trading_tickers = {"AAA", "BBB", "CCC", "DDD"}

        with patch("bot.paper_executor.PositionManager") as manager_cls, patch(
            "bot.paper_executor.PositionSizer"
        ) as sizer_cls:
            manager = manager_cls.return_value
            manager.evaluate.return_value = []
            manager.execute_sales.return_value = []
            sizer_cls.return_value.plan.return_value = []

            PaperExecutor().execute(
                self.portfolio, self.scan,
                eligible_buy_tickers={"AAA", "BBB", "CCC"},
            )

            calls = sizer_cls.return_value.plan.call_args_list
            self.assertEqual(len(calls), 2)
            second = [item.ticker for item in calls[1].kwargs["analyses"]]
            self.assertIn("CCC", second)
            self.assertNotIn("DDD", second)

    def test_none_preserves_legacy_candidate_selection_for_compatibility(self):
        with patch("bot.paper_executor.PositionManager") as manager_cls, patch(
            "bot.paper_executor.PositionSizer"
        ) as sizer_cls:
            manager = manager_cls.return_value
            manager.evaluate.return_value = []
            manager.execute_sales.return_value = []
            sizer_cls.return_value.plan.return_value = []

            PaperExecutor().execute(self.portfolio, self.scan)

            eligible = sizer_cls.return_value.plan.call_args.kwargs["analyses"]
            self.assertEqual([item.ticker for item in eligible], ["AAA", "BBB"])


if __name__ == "__main__":
    unittest.main()
