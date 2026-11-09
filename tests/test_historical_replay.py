from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from bot.historical_replay import HistoricalReplay, HistoricalReplayCycle, build_historical_cycles
from bot.virtual_portfolio import VirtualPortfolio


class CapturingExecutor:
    def __init__(self):
        self.timestamps = []

    def execute(self, portfolio, scan, *, eligible_buy_tickers=None,
                eligible_buy_reasons=None, as_of=None):
        self.timestamps.append(as_of)


def _cycle(timestamp, prices=None):
    return HistoricalReplayCycle(timestamp, SimpleNamespace(current_prices=prices or {}))


def test_replay_uses_historical_timestamp_and_reports_equity():
    executor = CapturingExecutor()
    portfolio = VirtualPortfolio(initial_balance=1000)
    result = HistoricalReplay(portfolio, executor).run([
        _cycle(datetime(2025, 1, 2, 10, tzinfo=timezone.utc))
    ])
    assert executor.timestamps == [datetime(2025, 1, 2, 10, tzinfo=timezone.utc)]
    assert result.final_equity == 1000
    assert result.total_return_pct == 0
    assert result.total_trades == 0


@pytest.mark.parametrize("timestamps", [
    [datetime(2025, 1, 2), datetime(2025, 1, 3)],
    [datetime(2025, 1, 3, tzinfo=timezone.utc), datetime(2025, 1, 2, tzinfo=timezone.utc)],
    [datetime(2025, 1, 2, tzinfo=timezone.utc)] * 2,
])
def test_replay_rejects_naive_or_nonincreasing_timestamps(timestamps):
    replay = HistoricalReplay(VirtualPortfolio(initial_balance=1000), CapturingExecutor())
    with pytest.raises(ValueError):
        replay.run([_cycle(value) for value in timestamps])


def test_missing_holding_quote_makes_equity_incomplete_not_fabricated():
    portfolio = VirtualPortfolio(initial_balance=1000)
    portfolio.buy("AAA", 1, 100, timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc))
    cycle = _cycle(datetime(2025, 1, 2, tzinfo=timezone.utc), {})
    result = HistoricalReplay(portfolio, CapturingExecutor()).run([cycle])
    assert result.final_equity is None
    assert "incomplete_mark_to_market_due_to_missing_quotes" in result.warnings
    assert result.equity_curve[0].unpriced_tickers == ("AAA",)


def test_build_cycles_never_forward_fills_prices_and_uses_only_visible_history(monkeypatch):
    import bot.stock_analysis as analysis_module
    import bot.intelligence.integration as integration_module

    seen_lengths = []

    class FakeAnalyzer:
        def __init__(self, **kwargs):
            pass

        def analyze(self, instrument_id, ticker, bars):
            seen_lengths.append(len(bars))
            return SimpleNamespace(ticker=ticker, score=0.2, momentum=0.0, volatility=0.1)

    monkeypatch.setattr(analysis_module, "StockAnalyzer", FakeAnalyzer)
    monkeypatch.setattr(integration_module, "analyze_scan", lambda scan: {
        ticker: SimpleNamespace(overall_score=0.1, overall_confidence=0.1, overall_consistency=0.1)
        for ticker in scan.analyses
    })

    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    bars = [
        SimpleNamespace(time=start + timedelta(days=i), close=100 + i)
        for i in range(3)
    ]
    cycles = build_historical_cycles(
        {"AAA": bars},
        instrument_ids={"AAA": "id"},
        lot_sizes={"AAA": 1},
        sessions_by_ticker={"AAA": {"session": "REGULAR", "instrument_exchange": "MOEX"}},
        tradable_tickers={"AAA"},
        min_history=2,
        momentum_period=1,
    )
    assert len(cycles) == 2
    assert [len(c.scan.candle_history["AAA"]) for c in cycles] == [2, 3]
    assert [c.scan.current_prices["AAA"] for c in cycles] == [101, 102]
    assert seen_lengths == [2, 3]
    assert cycles[0].timestamp < cycles[1].timestamp


def test_empty_replay_has_no_fabricated_final_equity():
    result = HistoricalReplay(VirtualPortfolio(initial_balance=1000), CapturingExecutor()).run([])
    assert result.final_equity is None
    assert result.total_return_pct is None
