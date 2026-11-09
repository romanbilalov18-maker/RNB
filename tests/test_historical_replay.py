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

    def test_build_cycles_uses_prior_closed_bars_and_current_open_for_execution(self):
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
                SimpleNamespace(time=start + timedelta(days=i), open=200 + i, close=100 + i)
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
        self.assertNotIn("AAA", cycles[1].scan.current_prices)
        self.assertEqual(cycles[2].scan.candle_history["AAA"], bars[:2])
        self.assertEqual(cycles[2].scan.current_prices["AAA"], 202)
        self.assertEqual(cycles[2].scan.previous_closes["AAA"], 101)
        self.assertEqual(seen_lengths, [2])
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
                SimpleNamespace(time=start + timedelta(days=i), open=100 + i, close=100 + i)
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
        self.assertEqual(cycles[-1].eligible_buy_tickers, {"AAA"})
        self.assertIn("AAA", cycles[-1].eligible_buy_reasons)

    def test_replay_runs_real_paper_executor_buy_sell_commission_and_profit_reserve(self):
        from bot.paper_executor import PaperExecutor
        from bot.stock_analysis import StockAnalysis

        initial_balance = 100_000.0
        portfolio = VirtualPortfolio(initial_balance, commission_rate=0.001)
        first = datetime(2025, 1, 2, 10, tzinfo=timezone.utc)
        second = datetime(2025, 1, 2, 11, tzinfo=timezone.utc)
        analysis = StockAnalysis(
            instrument_id="instrument-aaa",
            ticker="AAA",
            last_price=100.0,
            return_period=0.02,
            volatility=0.01,
            momentum=0.03,
            average_volume=1000.0,
            volume_ratio=1.2,
            trend_strength=0.02,
            score=0.9,
        )
        entry_scan = SimpleNamespace(
            analyses={"AAA": analysis},
            buy_candidates=[analysis],
            current_prices={"AAA": 100.0},
            previous_closes={"AAA": 99.0},
            lot_sizes={"AAA": 1},
            active_trading_tickers={"AAA"},
            fresh_quote_tickers={"AAA"},
            sellable_quote_tickers={"AAA"},
            session_by_ticker={
                "AAA": {"session": "REGULAR", "instrument_exchange": "MOEX"}
            },
            candle_history={},
            market_closed_tickers=set(),
        )
        exit_scan = SimpleNamespace(
            analyses={},
            buy_candidates=[],
            current_prices={"AAA": 110.0},
            previous_closes={"AAA": 100.0},
            lot_sizes={},
            active_trading_tickers={"AAA"},
            fresh_quote_tickers={"AAA"},
            sellable_quote_tickers={"AAA"},
            session_by_ticker={
                "AAA": {"session": "REGULAR", "instrument_exchange": "MOEX"}
            },
            candle_history={},
            market_closed_tickers=set(),
        )

        result = HistoricalReplay(portfolio, PaperExecutor()).run([
            HistoricalReplayCycle(first, entry_scan, {"AAA"}, {"AAA": "approved"}),
            HistoricalReplayCycle(second, exit_scan, set(), {}),
        ])

        self.assertEqual(result.buy_trades, 1)
        self.assertEqual(result.sell_trades, 1)
        self.assertEqual(result.total_trades, 2)
        self.assertEqual(result.equity_curve[0].open_positions, 1)
        self.assertEqual(result.equity_curve[1].open_positions, 0)
        self.assertGreater(result.realized_pnl, 0.0)
        self.assertGreater(result.commissions, 0.0)
        self.assertGreater(result.protected_cash, 0.0)
        self.assertAlmostEqual(
            result.final_equity,
            portfolio.cash + portfolio.protected_cash,
        )
        self.assertEqual(portfolio.trades[0].timestamp, first)
        self.assertEqual(portfolio.trades[1].timestamp, second)


if __name__ == "__main__":
    unittest.main()
