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
        self.assertIn("покупок=2, продаж=1", output)
        self.assertIn("Свободные деньги для торговли: 3.44 RUB", output)
        self.assertIn("Полнота оценки: НЕПОЛНАЯ", output)
        self.assertIn("НЕТ СВЕЖЕЙ ЦЕНЫ: BBB.", output)
        self.assertIn("2 инструментов", output)
        self.assertIn("1 рекомендаций", output)
        self.assertIn("не подтверждается", output)

    def test_readable_summary_reports_complete_valuation_and_no_trades(self):
        portfolio = SimpleNamespace(
            positions={"AAA": SimpleNamespace(quantity=1, average_price=10.0)}, cash=100.0,
            realized_pnl=0.0, commissions=0.0,
        )
        result = SimpleNamespace(current_prices={"AAA": 10.0})
        output = self.render(
            portfolio=portfolio, result=result, sell_trades=[], buy_trades=[],
            equity=110.0, equity_complete=True,
        )
        self.assertIn("сделок не было; покупок=0, продаж=0", output)
        self.assertIn("Полная стоимость портфеля (деньги + резерв + все позиции): 110.00 RUB", output)
        self.assertIn("Свежие подтверждённые котировки получены по всем открытым позициям.", output)

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
        self.assertIn("Свободные деньги + защищённый резерв: 910.00 RUB", output)
        self.assertIn("Текущая стоимость оценённых позиций: 24.00 RUB", output)
        self.assertIn("Нереализованный P/L оценённых позиций (до комиссии будущей продажи): +4.00 RUB", output)
        self.assertIn("ОБЩИЙ результат против старта: -66.00 RUB (-6.60%).", output)
        self.assertIn("повторно комиссии не вычитаются", output)

    def test_financial_summary_reports_cycle_profit_and_new_reserve_transfer(self):
        portfolio = SimpleNamespace(
            initial_balance=1000.0,
            positions={},
            cash=1080.0,
            protected_cash=20.0,
            realized_pnl=100.0,
            commissions=5.0,
            commission_rate=0.01,
        )
        result = SimpleNamespace(current_prices={})
        output = self.render(
            portfolio=portfolio,
            result=result,
            sell_trades=[
                SimpleNamespace(realized_pnl=40.0),
                SimpleNamespace(realized_pnl=-10.0),
            ],
            buy_trades=[],
            equity=1100.0,
            equity_complete=True,
            reserve_added_this_cycle=20.0,
        )
        self.assertIn("Отложено в резерв за этот цикл: 20.00 RUB", output)
        self.assertIn("Защищённый резерв прибыли на данный момент: 20.00 RUB", output)
        self.assertIn("Заработано за этот цикл на закрытых сделках (после комиссий): +30.00 RUB", output)
        self.assertIn("Положительная прибыль закрытых сделок до распределения: 40.00 RUB", output)
        self.assertIn("Всего реализованная прибыль/убыток за всё время: +100.00 RUB", output)

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
        self.assertIn("ОБЩИЙ P/L и доходность против старта: НЕ РАССЧИТЫВАЮТСЯ", output)
        self.assertIn("НЕТ СВЕЖЕЙ ЦЕНЫ: BBB.", output)
        self.assertIn("Их себестоимость по цене покупки", output)
        self.assertIn("BBB: количество=3; цена покупки=5.00; текущая цена, стоимость и P/L неизвестны.", output)


if __name__ == "__main__":
    unittest.main()
