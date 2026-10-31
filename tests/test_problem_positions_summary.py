import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from types import SimpleNamespace

from bot.main import _print_problem_positions_summary
from bot.virtual_portfolio import VirtualPortfolio


class ProblemPositionsSummaryTests(unittest.TestCase):
    def test_reports_missing_quote_and_broker_restriction_without_marking_market_value(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("HELD", 3, 100, datetime.now(timezone.utc))
        position = portfolio.positions["HELD"]
        position.quote_unavailable_cycles = 4
        position.stagnant_sessions = 2
        position.last_health_status = "QUOTE_UNAVAILABLE"
        result = SimpleNamespace(
            current_prices={},
            instrument_status_by_ticker={
                "HELD": {
                    "resolution": "RESOLVED",
                    "trading_status": "NOT_AVAILABLE_FOR_TRADING",
                    "api_trade_available": False,
                    "sell_available": True,
                    "status_check_succeeded": True,
                }
            },
        )

        output = StringIO()
        with redirect_stdout(output):
            _print_problem_positions_summary(portfolio, result)
        report = output.getvalue()

        self.assertIn("Позиций требуют внимания: 1 из 1", report)
        self.assertIn("HELD", report)
        self.assertIn("quote_unavailable_cycles=4", report)
        self.assertIn("api_trade_available=False", report)
        self.assertIn("свежей подтверждённой цены нет", report)
        self.assertIn("ручная проверка инструмента", report)
        self.assertIn("автоматическая продажа только из-за этих признаков запрещена", report)

    def test_does_not_flag_healthy_position_or_claim_missing_market_price(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("OK", 1, 50, datetime.now(timezone.utc))
        portfolio.positions["OK"].quote_unavailable_cycles = 0
        portfolio.positions["OK"].last_health_status = "NORMAL_MONITORING"
        result = SimpleNamespace(
            current_prices={"OK": 51.0},
            instrument_status_by_ticker={
                "OK": {"resolution": "RESOLVED", "api_trade_available": True}
            },
        )

        output = StringIO()
        with redirect_stdout(output):
            _print_problem_positions_summary(portfolio, result)
        report = output.getvalue()

        self.assertIn("Позиций требуют внимания: 0 из 1", report)
        self.assertIn("Проблемных позиций", report)
        self.assertNotIn("OK: quantity=", report)


if __name__ == "__main__":
    unittest.main()
