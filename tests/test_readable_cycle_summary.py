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
