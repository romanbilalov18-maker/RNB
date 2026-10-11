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
