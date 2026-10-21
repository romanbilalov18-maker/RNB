import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace

from bot.main import _print_readable_cycle_summary


class ReadableCycleSummaryTests(unittest.TestCase):
    def render(self, **kwargs):
        output = io.StringIO()
        with redirect_stdout(output):
            _print_readable_cycle_summary(**kwargs)
        return output.getvalue()

    def test_readable_summary_reports_cash_trades_and_partial_valuation(self):
        portfolio = SimpleNamespace(
            positions={"AAA": object(), "BBB": object()},
            cash=3.44, realized_pnl=953.99, commissions=45.03,
        )
        result = SimpleNamespace(current_prices={"AAA": 10.0})
        output = self.render(
            portfolio=portfolio, result=result,
            sell_trades=[object()], buy_trades=[object(), object()],
            equity=500.0, equity_complete=False,
            intelligence_results={"AAA": object(), "BBB": object()},
            decisions={"AAA": object()},
        )
        self.assertIn("виртуальная торговля", output)
        self.assertIn("покупок — 2, продаж — 1, всего — 3", output)
        self.assertIn("Свободные деньги: 3.44 RUB", output)
        self.assertIn("НЕПОЛНАЯ оценка", output)
        self.assertIn("Нет свежих котировок для: BBB.", output)
        self.assertIn("2 инструментов", output)
        self.assertIn("1 рекомендаций", output)
        self.assertIn("не подтверждается", output)

    def test_readable_summary_reports_complete_valuation_and_no_trades(self):
        portfolio = SimpleNamespace(
            positions={"AAA": object()}, cash=100.0,
            realized_pnl=0.0, commissions=0.0,
        )
        result = SimpleNamespace(current_prices={"AAA": 10.0})
        output = self.render(
            portfolio=portfolio, result=result, sell_trades=[], buy_trades=[],
            equity=110.0, equity_complete=True,
        )
        self.assertIn("анализ выполнен, сделок нет", output)
        self.assertIn("Стоимость портфеля по доступным ценам: 110.00 RUB (оценка полная)", output)
        self.assertIn("Свежие котировки есть для всех открытых позиций.", output)

    def test_financial_summary_shows_complete_money_breakdown_without_double_subtracting_fees(self):
        portfolio = SimpleNamespace(
            initial_balance=1000.0,
            positions={"AAA": SimpleNamespace(quantity=2, average_price=10.0)},
            cash=900.0, protected_cash=10.0, realized_pnl=4.0, commissions=1.0,
            commission_rate=0.01, profit_reserve_rate=0.5,
        )
        result = SimpleNamespace(current_prices={"AAA": 12.0})
        output = self.render(
            portfolio=portfolio, result=result, sell_trades=[], buy_trades=[],
            equity=934.0, equity_complete=True,
        )
        self.assertIn("Стартовый капитал: 1000.00 RUB", output)
        self.assertIn("Все денежные средства вместе с резервом: 910.00 RUB", output)
        self.assertIn("Стоимость позиций с подтверждёнными свежими ценами: 24.00 RUB", output)
        self.assertIn("Нереализованный P/L по оценённым позициям до комиссии будущей продажи: +4.00 RUB", output)
        self.assertIn("ОБЩИЙ результат относительно старта: -66.00 RUB (-6.60%).", output)
        self.assertIn("комиссии повторно не вычитаются", output)

    def test_financial_summary_does_not_claim_total_result_when_quote_is_missing(self):
        portfolio = SimpleNamespace(
            initial_balance=1000.0,
            positions={
                "AAA": SimpleNamespace(quantity=2, average_price=10.0),
                "BBB": SimpleNamespace(quantity=3, average_price=5.0),
            },
            cash=900.0, protected_cash=10.0, realized_pnl=4.0, commissions=1.0,
            commission_rate=0.01,
        )
        result = SimpleNamespace(current_prices={"AAA": 12.0})
        output = self.render(
            portfolio=portfolio, result=result, sell_trades=[], buy_trades=[],
            equity=934.0, equity_complete=False,
        )
        self.assertIn("ОБЩИЙ результат и доходность: НЕ РАССЧИТЫВАЮТСЯ", output)
        self.assertIn("Позиции без свежей подтверждённой котировки: BBB.", output)
        self.assertIn("себестоимость позиций без свежей цены", output.lower())
        self.assertIn("BBB: количество=3; средняя покупка=5.00; текущая цена/стоимость/P&L неизвестны.", output)


if __name__ == "__main__":
    unittest.main()
