from types import SimpleNamespace

from bot.main import _print_readable_cycle_summary


def test_readable_summary_reports_cash_trades_and_partial_valuation(capsys):
    portfolio = SimpleNamespace(
        positions={"AAA": object(), "BBB": object()},
        cash=3.44,
        realized_pnl=953.99,
        commissions=45.03,
    )
    result = SimpleNamespace(current_prices={"AAA": 10.0})
    _print_readable_cycle_summary(
        portfolio=portfolio,
        result=result,
        sell_trades=[object()],
        buy_trades=[object(), object()],
        equity=500.0,
        equity_complete=False,
        intelligence_results={"AAA": object(), "BBB": object()},
        decisions={"AAA": object()},
    )

    output = capsys.readouterr().out
    assert "виртуальная торговля" in output
    assert "покупок — 2, продаж — 1, всего — 3" in output
    assert "Свободные деньги: 3.44 RUB" in output
    assert "НЕПОЛНАЯ оценка" in output
    assert "Нет свежих котировок для: BBB." in output
    assert "2 инструментов" in output
    assert "1 рекомендаций" in output
    assert "не подтверждается" in output


def test_readable_summary_reports_complete_valuation_and_no_trades(capsys):
    portfolio = SimpleNamespace(
        positions={"AAA": object()},
        cash=100.0,
        realized_pnl=0.0,
        commissions=0.0,
    )
    result = SimpleNamespace(current_prices={"AAA": 10.0})
    _print_readable_cycle_summary(
        portfolio=portfolio,
        result=result,
        sell_trades=[],
        buy_trades=[],
        equity=110.0,
        equity_complete=True,
    )

    output = capsys.readouterr().out
    assert "анализ выполнен, сделок нет" in output
    assert "Стоимость портфеля по доступным ценам: 110.00 RUB (оценка полная)" in output
    assert "Свежие котировки есть для всех открытых позиций." in output


def test_financial_summary_shows_complete_money_breakdown_without_double_subtracting_fees(capsys):
    portfolio = SimpleNamespace(
        initial_balance=1000.0,
        positions={"AAA": SimpleNamespace(quantity=2, average_price=10.0)},
        cash=900.0, protected_cash=10.0, realized_pnl=4.0, commissions=1.0,
        commission_rate=0.01, profit_reserve_rate=0.5,
    )
    result = SimpleNamespace(current_prices={"AAA": 12.0})
    _print_readable_cycle_summary(
        portfolio=portfolio, result=result, sell_trades=[], buy_trades=[],
        equity=934.0, equity_complete=True,
    )
    output = capsys.readouterr().out
    assert "Стартовый капитал: 1000.00 RUB" in output
    assert "Все денежные средства вместе с резервом: 910.00 RUB" in output
    assert "Стоимость позиций с подтверждёнными свежими ценами: 24.00 RUB" in output
    assert "Нереализованный P/L по оценённым позициям до комиссии будущей продажи: +4.00 RUB" in output
    assert "ОБЩИЙ результат относительно старта: -66.00 RUB (-6.60%)." in output
    assert "комиссии повторно не вычитаются" in output


def test_financial_summary_does_not_claim_total_result_when_quote_is_missing(capsys):
    portfolio = SimpleNamespace(
        initial_balance=1000.0,
        positions={"AAA": SimpleNamespace(quantity=2, average_price=10.0),
                   "BBB": SimpleNamespace(quantity=3, average_price=5.0)},
        cash=900.0, protected_cash=10.0, realized_pnl=4.0, commissions=1.0,
        commission_rate=0.01,
    )
    result = SimpleNamespace(current_prices={"AAA": 12.0})
    _print_readable_cycle_summary(
        portfolio=portfolio, result=result, sell_trades=[], buy_trades=[],
        equity=934.0, equity_complete=False,
    )
    output = capsys.readouterr().out
    assert "ОБЩИЙ результат и доходность: НЕ РАССЧИТЫВАЮТСЯ" in output
    assert "Позиции без свежей подтверждённой котировки: BBB." in output
    assert "себестоимость позиций без свежей цены" in output.lower()
    assert "BBB: количество=3; средняя покупка=5.00; текущая цена/стоимость/P&L неизвестны." in output
