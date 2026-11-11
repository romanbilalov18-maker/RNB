import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bot.intelligence.decision_engine import DecisionEngine
from bot.main import _filter_intelligence_to_active_tickers
from bot.paper_executor import PaperExecutor


class LiveDecisionExecutionPathTests(unittest.TestCase):
    def test_only_active_buy_decisions_reach_paper_sizer(self):
        intelligence = {
            "AAA": SimpleNamespace(overall_score=0.9, overall_confidence=0.8, overall_consistency=0.8),
            "BBB": SimpleNamespace(overall_score=0.99, overall_confidence=0.99, overall_consistency=0.99),
        }
        filtered = _filter_intelligence_to_active_tickers(intelligence, {"AAA"})
        decisions = DecisionEngine().evaluate(filtered)
        buys = {ticker for ticker, decision in decisions.items() if decision.action == "BUY"}
        analyses = {
            ticker: SimpleNamespace(ticker=ticker, volatility=0.02, momentum=0.03, trend_strength=1.0)
            for ticker in ("AAA", "BBB")
        }
        scan = SimpleNamespace(
            analyses=analyses, buy_candidates=[analyses["AAA"], analyses["BBB"]],
            current_prices={"AAA": 10.0, "BBB": 20.0}, lot_sizes={"AAA": 1, "BBB": 1},
            active_trading_tickers={"AAA"}, fresh_quote_tickers={"AAA"},
        )
        portfolio = SimpleNamespace(
            positions={}, trades=[], cash=1000.0, commission_rate=0.001,
            equity=lambda prices: 1000.0,
        )
        with patch("bot.paper_executor.PositionManager") as manager_cls, patch(
            "bot.paper_executor.PositionSizer"
        ) as sizer_cls:
            manager_cls.return_value.evaluate.return_value = []
            manager_cls.return_value.execute_sales.return_value = []
            sizer_cls.return_value.plan.return_value = []
            PaperExecutor().execute(portfolio, scan, eligible_buy_tickers=buys)
            planned = sizer_cls.return_value.plan.call_args.kwargs["analyses"]
        self.assertEqual(buys, {"AAA"})
        self.assertEqual([item.ticker for item in planned], ["AAA"])

    def test_empty_active_allowlist_produces_no_decisions_or_execution(self):
        intelligence = {"AAA": SimpleNamespace(
            overall_score=0.99, overall_confidence=0.99, overall_consistency=0.99
        )}
        filtered = _filter_intelligence_to_active_tickers(intelligence, set())
        self.assertEqual(DecisionEngine().evaluate(filtered), {})
        scan = SimpleNamespace(
            analyses={}, buy_candidates=[], current_prices={}, lot_sizes={},
            active_trading_tickers=set(), fresh_quote_tickers=set(),
        )
        portfolio = SimpleNamespace(
            positions={}, trades=[], cash=1000.0, commission_rate=0.001,
            equity=lambda prices: 1000.0,
        )
        with patch("bot.paper_executor.PositionManager") as manager_cls, patch(
            "bot.paper_executor.PositionSizer"
        ) as sizer_cls:
            self.assertEqual(PaperExecutor().execute(
                portfolio, scan, eligible_buy_tickers=set()
            ), ([], []))
            manager_cls.return_value.evaluate.assert_not_called()
            sizer_cls.return_value.plan.assert_not_called()


if __name__ == "__main__":
    unittest.main()
