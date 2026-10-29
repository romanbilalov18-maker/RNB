import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from types import SimpleNamespace

from bot.main import _print_end_of_run_report
from bot.virtual_portfolio import VirtualPortfolio


class EndOfRunReportTests(unittest.TestCase):
    def test_reports_run_scoped_trades_profit_fees_and_reserve(self):
        portfolio = VirtualPortfolio(10_000, commission_rate=0.001)
        timestamp = datetime(2026, 10, 29, 10, 0, tzinfo=timezone.utc)
        portfolio.buy("AAA", 10, 100.0, timestamp)

        starting_trade_count = len(portfolio.trades)
        starting_realized_pnl = portfolio.realized_pnl
        starting_commissions = portfolio.commissions
        starting_reserve = portfolio.protected_cash

        portfolio.sell("AAA", 10, 110.0, timestamp)

        output = io.StringIO()
        with redirect_stdout(output):
            _print_end_of_run_report(
                portfolio=portfolio,
                starting_trade_count=starting_trade_count,
                starting_realized_pnl=starting_realized_pnl,
                starting_commissions=starting_commissions,
                starting_reserve=starting_reserve,
                elapsed_minutes=5.0,
                cycles_started=2,
                last_result=SimpleNamespace(current_prices={}),
            )

        report = output.getvalue()
        self.assertIn("ИТОГ ВСЕГО ЗАПУСКА", report)
        self.assertIn("Сделок за этот запуск: 1 (покупок=0, продаж=1)", report)
        self.assertIn("Реализованный P/L за запуск: +97.90 RUB", report)
        self.assertIn("Комиссии за запуск: 1.10 RUB", report)
        self.assertIn("Изменение защищённого резерва за запуск: 68.53 RUB", report)
        self.assertIn("Полнота оценки: ПОЛНАЯ", report)

    def test_missing_final_quote_is_reported_as_incomplete_not_zero_value(self):
        portfolio = VirtualPortfolio(10_000, commission_rate=0.001)
        portfolio.buy("UNPRICED", 2, 50.0, datetime.now(timezone.utc))

        output = io.StringIO()
        with redirect_stdout(output):
            _print_end_of_run_report(
                portfolio=portfolio,
                starting_trade_count=len(portfolio.trades),
                starting_realized_pnl=portfolio.realized_pnl,
                starting_commissions=portfolio.commissions,
                starting_reserve=portfolio.protected_cash,
                elapsed_minutes=1.0,
                cycles_started=1,
                last_result=None,
            )

        report = output.getvalue()
        self.assertIn("позиции без свежих цен: UNPRICED", report)
        self.assertIn("Полнота оценки: НЕПОЛНАЯ", report)
        self.assertIn("текущая цена, стоимость и P/L неизвестны", report)
        self.assertIn("ОБЩИЙ P/L и доходность против старта: НЕ РАССЧИТЫВАЮТСЯ", report)


if __name__ == "__main__":
    unittest.main()
