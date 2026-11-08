import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from bot.main import _evaluate_position_exit_decisions
from bot.virtual_portfolio import VirtualPortfolio


class PositionExitReportConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.portfolio = VirtualPortfolio(10_000, commission_rate=0.001)
        self.portfolio.buy(
            "AAA", 10, 100.0, datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
        )

    def test_report_uses_net_take_profit_after_entry_and_exit_commissions(self):
        result = SimpleNamespace(analyses={}, current_prices={"AAA": 100.26})

        decisions = _evaluate_position_exit_decisions(
            self.portfolio, result, take_profit_percent=0.15
        )

        self.assertEqual(decisions[0].action, "SELL")
        self.assertIn("Take Profit", decisions[0].reason)

    def test_report_holds_below_net_take_profit_threshold(self):
        result = SimpleNamespace(analyses={}, current_prices={"AAA": 100.25})

        decisions = _evaluate_position_exit_decisions(
            self.portfolio, result, take_profit_percent=0.15
        )

        self.assertEqual(decisions[0].action, "HOLD")

    def test_report_uses_stop_loss_configured_by_shared_manager(self):
        result = SimpleNamespace(analyses={}, current_prices={"AAA": 94.0})

        decisions = _evaluate_position_exit_decisions(
            self.portfolio, result, take_profit_percent=0.15
        )

        self.assertEqual(decisions[0].action, "SELL")
        self.assertIn("лимит убытка", decisions[0].reason)

    def test_missing_quote_is_hold_not_a_sell_signal(self):
        result = SimpleNamespace(analyses={}, current_prices={})

        decisions = _evaluate_position_exit_decisions(
            self.portfolio, result, take_profit_percent=0.15
        )

        self.assertEqual(decisions[0].action, "HOLD")
        self.assertIn("валидной цены", decisions[0].reason)


if __name__ == "__main__":
    unittest.main()
