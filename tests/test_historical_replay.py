from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

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


class HistoricalReplayTests(unittest.TestCase):
    def test_replay_uses_historical_timestamp_and_reports_equity(self):
        executor = CapturingExecutor()
        portfolio = VirtualPortfolio(initial_balance=1000)
        timestamp = datetime(2025, 1, 2, 10, tzinfo=timezone.utc)
        result = HistoricalReplay(portfolio, executor).run([_cycle(timestamp)])
        self.assertEqual(executor.timestamps, [timestamp])
        self.assertEqual(result.final_equity, 1000)
        self.assertEqual(result.total_return_pct, 0)
        self.assertEqual(result.total_trades, 0)

    def test_replay_rejects_naive_or_nonincreasing_timestamps(self):
        cases = [
            [datetime(2025, 1, 2), datetime(2025, 1, 3)],
            [datetime(2025, 1, 3, tzinfo=timezone.utc), datetime(2025, 1, 2, tzinfo=timezone.utc)],
            [datetime(2025, 1, 2, tzinfo=timezone.utc)] * 2,
        ]
        replay = HistoricalReplay(VirtualPortfolio(initial_balance=1000), CapturingExecutor())
        for timestamps in cases:
            with self.subTest(timestamps=timestamps), self.assertRaises(ValueError):
                replay.run([_cycle(value) for value in timestamps])

    def test_missing_holding_quote_makes_equity_incomplete_not_fabricated(self):
        portfolio = VirtualPortfolio(initial_balance=1000)
        portfolio.buy("AAA", 1, 100, timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc))
        result = HistoricalReplay(portfolio, CapturingExecutor()).run([
            _cycle(datetime(2025, 1, 2, tzinfo=timezone.utc), {})
        ])
        self.assertIsNone(result.final_equity)
        self.assertIn("incomplete_mark_to_market_due_to_missing_quotes", result.warnings)
        self.assertEqual(result.equity_curve[0].unpriced_tickers, ("AAA",))

    def test_build_cycles_never_forward_fills_prices_and_uses_only_visible_history(self):
        import bot.stock_analysis as analysis_module
        import bot.intelligence.integration as integration_module

        seen_lengths = []

        class FakeAnalyzer:
            def __init__(self, **kwargs):
                pass

            def analyze(self, instrument_id, ticker, bars):
                seen_lengths.append(len(bars))
                return SimpleNamespace(ticker=ticker, score=0.2, momentum=0.0, volatility=0.1)

        fake_intelligence = lambda scan: {
            ticker: SimpleNamespace(overall_score=0.1, overall_confidence=0.1, overall_consistency=0.1)
            for ticker in scan.analyses
        }
        with patch.object(analysis_module, "StockAnalyzer", FakeAnalyzer), patch.object(
            integration_module, "analyze_scan", fake_intelligence
        ):
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

        self.assertEqual(len(cycles), 3)
        self.assertNotIn("AAA", cycles[0].scan.current_prices)
        self.assertEqual([len(c.scan.candle_history["AAA"]) for c in cycles[1:]], [2, 3])
        self.assertEqual([c.scan.current_prices["AAA"] for c in cycles[1:]], [101, 102])
        self.assertEqual(seen_lengths, [2, 3])
        self.assertLess(cycles[0].timestamp, cycles[1].timestamp)
        self.assertLess(cycles[1].timestamp, cycles[2].timestamp)

    def test_empty_replay_has_no_fabricated_final_equity(self):
        result = HistoricalReplay(VirtualPortfolio(initial_balance=1000), CapturingExecutor()).run([])
        self.assertIsNone(result.final_equity)
        self.assertIsNone(result.total_return_pct)


    def test_build_cycles_passes_only_decision_engine_approved_buy_tickers(self):
        import bot.stock_analysis as analysis_module
        import bot.intelligence.integration as integration_module

        class FakeAnalyzer:
            def __init__(self, **kwargs):
                pass

            def analyze(self, instrument_id, ticker, bars):
                return SimpleNamespace(
                    ticker=ticker, score=0.9, momentum=0.1, volatility=0.1
                )

        def fake_intelligence(scan):
            return {
                ticker: SimpleNamespace(
                    overall_score=0.9,
                    overall_confidence=0.8,
                    overall_consistency=0.8,
                )
                for ticker in scan.analyses
            }

        with patch.object(analysis_module, "StockAnalyzer", FakeAnalyzer), patch.object(
            integration_module, "analyze_scan", fake_intelligence
        ):
            start = datetime(2025, 1, 1, tzinfo=timezone.utc)
            bars = [
                SimpleNamespace(time=start + timedelta(days=i), close=100 + i)
                for i in range(2)
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

        self.assertEqual(len(cycles), 2)
        self.assertEqual(cycles[-1].eligible_buy_tickers, {"AAA"})
        self.assertIn("AAA", cycles[-1].eligible_buy_reasons)


if __name__ == "__main__":
    unittest.main()
