from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bot.historical_replay import (
    HistoricalReplay, HistoricalReplayCycle, build_historical_cycles,
    iter_historical_cycles,
)
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

        fake_intelligence = lambda scan, portfolio=None: {
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
                sessions_by_ticker={"AAA": {
                    "session": "main", "instrument_exchange": "MOEX",
                    "verified": True, "is_open": True, "schedule_date": "2025-01-03",
                }},
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


    def test_historical_buy_requires_verified_open_schedule_for_exact_bar_date(self):
        from bot.historical_replay import _historical_session_is_open
        self.assertTrue(_historical_session_is_open({
            "verified": True, "is_open": True, "schedule_date": "2025-01-03",
            "session": "main", "instrument_exchange": "MOEX",
        }, "2025-01-03"))
        for invalid in (
            {"verified": False, "is_open": True, "schedule_date": "2025-01-03",
             "session": "main", "instrument_exchange": "MOEX"},
            {"verified": True, "is_open": False, "schedule_date": "2025-01-03",
             "session": "closed", "instrument_exchange": "MOEX"},
            {"verified": True, "is_open": True, "schedule_date": "2025-01-04",
             "session": "main", "instrument_exchange": "MOEX"},
            {"session": "main", "instrument_exchange": "MOEX"},
        ):
            with self.subTest(invalid=invalid):
                self.assertFalse(_historical_session_is_open(invalid, "2025-01-03"))

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

        def fake_intelligence(scan, portfolio=None):
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
                sessions_by_ticker={"AAA": {"session": "main", "instrument_exchange": "MOEX", "verified": True, "is_open": True, "schedule_date": "2025-01-03"}},
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


    def test_streamed_cycles_receive_portfolio_state_after_previous_execution(self):
        import bot.stock_analysis as analysis_module
        import bot.intelligence.integration as integration_module

        class FakeAnalyzer:
            def __init__(self, **kwargs):
                pass

            def analyze(self, instrument_id, ticker, bars):
                return SimpleNamespace(ticker=ticker, score=0.9, momentum=0.1, volatility=0.1)

        observed_positions = []

        def fake_intelligence(scan, portfolio=None):
            observed_positions.append(set(portfolio.positions) if portfolio is not None else None)
            return {
                ticker: SimpleNamespace(
                    overall_score=0.9,
                    overall_confidence=0.8,
                    overall_consistency=0.8,
                )
                for ticker in scan.analyses
            }

        portfolio = VirtualPortfolio(initial_balance=10_000)
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        bars = [
            SimpleNamespace(time=start + timedelta(days=i), open=100 + i, close=100 + i)
            for i in range(4)
        ]

        with patch.object(analysis_module, "StockAnalyzer", FakeAnalyzer), patch.object(
            integration_module, "analyze_scan", fake_intelligence
        ):
            cycles = iter_historical_cycles(
                {"AAA": bars},
                instrument_ids={"AAA": "id"},
                lot_sizes={"AAA": 1},
                sessions_by_ticker={"AAA": {"session": "REGULAR", "instrument_exchange": "MOEX"}},
                tradable_tickers={"AAA"},
                min_history=2,
                momentum_period=1,
                portfolio=portfolio,
            )
            next(cycles)
            next(cycles)
            next(cycles)
            portfolio.buy("AAA", 1, 102.0, start + timedelta(days=2))
            next(cycles)

        self.assertEqual(observed_positions, [set(), set(), set(), {"AAA"}])


    def test_replay_consumes_stateful_cycle_generator_after_each_execution(self):
        events = []

        class OrderedExecutor:
            def execute(self, portfolio, scan, *, eligible_buy_tickers=None,
                        eligible_buy_reasons=None, as_of=None):
                events.append(("execute", as_of))

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)

        def cycles():
            events.append(("prepare", 1))
            yield _cycle(start)
            events.append(("prepare", 2))
            yield _cycle(start + timedelta(days=1))

        result = HistoricalReplay(
            VirtualPortfolio(initial_balance=1000), OrderedExecutor()
        ).run(cycles())

        self.assertEqual(
            events,
            [
                ("prepare", 1),
                ("execute", start),
                ("prepare", 2),
                ("execute", start + timedelta(days=1)),
            ],
        )
        self.assertEqual(len(result.equity_curve), 2)


    def test_confidence_breakdown_includes_individual_analyzers_for_all_levels(self):
        from bot.historical_replay import _confidence_breakdown

        intelligence = SimpleNamespace(
            level_08=SimpleNamespace(
                confidence=0.4,
                analyzer_results={
                    "cross_asset_context": SimpleNamespace(confidence=0.2),
                },
            ),
            level_09=SimpleNamespace(
                confidence=0.3,
                analyzer_results={
                    "opportunity_priority": SimpleNamespace(confidence=0.1),
                    "correlation_risk": SimpleNamespace(confidence=0.0),
                },
            ),
            level_10=SimpleNamespace(
                confidence=0.5,
                analyzer_results={
                    "cross_level_agreement": SimpleNamespace(confidence=0.25),
                },
            ),
            level_11=SimpleNamespace(
                confidence=0.0,
                analyzer_results=(
                    SimpleNamespace(analyzer="learning_confidence", confidence=0.0),
                ),
            ),
            level_14=SimpleNamespace(
                confidence=0.35,
                analyzer_results=(
                    SimpleNamespace(analyzer="data_reliability", confidence=0.7),
                ),
            ),
        )

        breakdown = _confidence_breakdown(intelligence)

        self.assertEqual(breakdown["L08.cross_asset_context"], 0.2)
        self.assertEqual(breakdown["L09.opportunity_priority"], 0.1)
        self.assertEqual(breakdown["L09.correlation_risk"], 0.0)
        self.assertEqual(breakdown["L10.cross_level_agreement"], 0.25)
        self.assertEqual(breakdown["L11.learning_confidence"], 0.0)
        self.assertEqual(breakdown["L14.data_reliability"], 0.7)

    def test_historical_scan_builds_market_benchmark_from_observed_cycle_returns(self):
        import bot.stock_analysis as analysis_module
        import bot.intelligence.integration as integration_module

        class FakeAnalyzer:
            def __init__(self, **kwargs):
                pass

            def analyze(self, instrument_id, ticker, bars):
                return SimpleNamespace(
                    ticker=ticker, score=0.5, momentum=0.0, volatility=0.1
                )

        def fake_intelligence(scan, portfolio=None):
            return {
                ticker: SimpleNamespace(
                    overall_score=0.1, overall_confidence=0.1, overall_consistency=0.1
                )
                for ticker in scan.analyses
            }

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        bars_by_ticker = {
            "AAA": [
                SimpleNamespace(time=start + timedelta(days=0), open=100, close=100),
                SimpleNamespace(time=start + timedelta(days=1), open=102, close=101),
                SimpleNamespace(time=start + timedelta(days=2), open=102, close=102),
            ],
            "BBB": [
                SimpleNamespace(time=start + timedelta(days=0), open=100, close=100),
                SimpleNamespace(time=start + timedelta(days=1), open=101, close=100),
                SimpleNamespace(time=start + timedelta(days=2), open=101, close=101),
            ],
            "CCC": [
                SimpleNamespace(time=start + timedelta(days=0), open=100, close=100),
                SimpleNamespace(time=start + timedelta(days=1), open=99, close=100),
                SimpleNamespace(time=start + timedelta(days=2), open=99, close=99),
            ],
        }

        with patch.object(analysis_module, "StockAnalyzer", FakeAnalyzer), patch.object(
            integration_module, "analyze_scan", fake_intelligence
        ):
            cycles = list(iter_historical_cycles(
                bars_by_ticker,
                instrument_ids={ticker: ticker for ticker in bars_by_ticker},
                lot_sizes={ticker: 1 for ticker in bars_by_ticker},
                sessions_by_ticker={
                    ticker: {"instrument_exchange": "MOEX"}
                    for ticker in bars_by_ticker
                },
                tradable_tickers=set(bars_by_ticker),
                min_history=2,
                momentum_period=1,
                sectors_by_ticker={ticker: "technology" for ticker in bars_by_ticker},
            ))

        # The first two bars establish the required analysis history; the
        # third bar supplies the execution opens measured against the second
        # bar's completed closes.
        scan = cycles[-1].scan
        expected_returns = (102 / 101 - 1, 101 / 100 - 1, 99 / 100 - 1)
        self.assertAlmostEqual(scan.market_return, sum(expected_returns) / 3)
        self.assertAlmostEqual(scan.market_breadth, 2 / 3)
        self.assertEqual(scan.market_sample_count, 3)

    def test_historical_cycles_carry_explicit_sector_metadata_into_scan(self):
        import bot.stock_analysis as analysis_module
        import bot.intelligence.integration as integration_module

        class FakeAnalyzer:
            def __init__(self, **kwargs):
                pass

            def analyze(self, instrument_id, ticker, bars):
                return SimpleNamespace(ticker=ticker, score=0.5, momentum=0.0, volatility=0.1)

        with patch.object(analysis_module, "StockAnalyzer", FakeAnalyzer), patch.object(
            integration_module, "analyze_scan",
            lambda scan, portfolio=None: {
                ticker: SimpleNamespace(
                    overall_score=0.1, overall_confidence=0.1, overall_consistency=0.1
                )
                for ticker in scan.analyses
            },
        ):
            start = datetime(2025, 1, 1, tzinfo=timezone.utc)
            bars = [
                SimpleNamespace(time=start + timedelta(days=i), open=100 + i, close=100 + i)
                for i in range(3)
            ]
            cycles = list(iter_historical_cycles(
                {"AAA": bars},
                instrument_ids={"AAA": "id"},
                lot_sizes={"AAA": 1},
                sessions_by_ticker={"AAA": {"instrument_exchange": "MOEX"}},
                tradable_tickers={"AAA"},
                min_history=2,
                momentum_period=1,
                sectors_by_ticker={"AAA": "technology"},
            ))

        self.assertEqual(cycles[-1].scan.sector_by_ticker, {"AAA": "technology"})


    def test_walk_forward_learning_releases_only_after_three_later_sessions(self):
        import bot.stock_analysis as analysis_module
        import bot.intelligence.integration as integration_module
        import bot.intelligence.decision_engine as decision_module

        observed_sample_counts = []

        class FakeAnalyzer:
            def __init__(self, **kwargs):
                pass

            def analyze(self, instrument_id, ticker, bars):
                return SimpleNamespace(ticker=ticker, score=0.9, momentum=0.1, volatility=0.1)

        class FakeDecisionEngine:
            def evaluate(self, intelligence, held_tickers=()):
                return {"AAA": SimpleNamespace(
                    action="BUY", reason="test", score=0.9,
                    confidence=0.8, consistency=0.8,
                )}

        def fake_intelligence(scan, portfolio=None, learning_observations_by_ticker=None):
            samples = (learning_observations_by_ticker or {}).get("AAA", ())
            observed_sample_counts.append(len(samples))
            return {"AAA": SimpleNamespace(
                overall_score=0.9,
                overall_confidence=0.8,
                overall_consistency=0.8,
                level_01=SimpleNamespace(
                    score=0.8,
                    analyzer_results={
                        "trend": SimpleNamespace(analyzer="trend", score=0.8)
                    },
                ),
                level_03=SimpleNamespace(metadata={"regime": "trend"}),
            )}

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        bars = [
            SimpleNamespace(
                time=start + timedelta(days=i),
                open=100.0 + i,
                high=102.0 + i,
                low=99.0 + i,
                close=101.0 + i,
                volume=1000,
            )
            for i in range(9)
        ]
        with patch.object(analysis_module, "StockAnalyzer", FakeAnalyzer), patch.object(
            integration_module, "analyze_scan", fake_intelligence
        ), patch.object(decision_module, "DecisionEngine", FakeDecisionEngine):
            cycles = list(iter_historical_cycles(
                {"AAA": bars},
                instrument_ids={"AAA": "id"},
                lot_sizes={"AAA": 1},
                sessions_by_ticker={"AAA": {"instrument_exchange": "MOEX"}},
                tradable_tickers={"AAA"},
                min_history=2,
                momentum_period=1,
            ))

        # First possible decision is on bar index 2. Its outcome uses the close
        # of the third strictly later broker session (bar index 5), and becomes
        # available only to the following decision cycle (bar index 6).
        self.assertEqual(observed_sample_counts[:4], [0, 0, 0, 0])
        self.assertEqual(observed_sample_counts[4:6], [0, 0])
        self.assertEqual(observed_sample_counts[6:8], [1, 2])
        self.assertTrue(all(count >= 0 for count in observed_sample_counts))
        self.assertEqual(len(cycles), 9)

    def test_decision_diagnostics_count_actions_reasons_and_metric_ranges(self):
        from bot.historical_replay import _summarize_decision_diagnostics

        summary = _summarize_decision_diagnostics([
            {"ticker": "AAA", "action": "WAIT", "reason": "low score",
             "score": 0.2, "confidence": 0.8, "consistency": 0.7},
            {"ticker": "BBB", "action": "BUY", "reason": "approved",
             "score": 0.9, "confidence": 0.9, "consistency": 0.8},
            {"ticker": "CCC", "action": "WAIT", "reason": "low score",
             "score": 0.4, "confidence": 0.6, "consistency": 0.5},
            {"ticker": "DDD", "action": "NO_INTELLIGENCE",
             "reason": "missing result", "score": None,
             "confidence": None, "consistency": None},
        ])

        self.assertEqual(summary["candidate_decisions"], 4)
        self.assertEqual(summary["action_counts"], {
            "BUY": 1, "NO_INTELLIGENCE": 1, "WAIT": 2,
        })
        self.assertEqual(summary["reason_counts"]["low score"], 2)
        self.assertEqual(summary["metric_summary"]["score"]["observations"], 3)
        self.assertAlmostEqual(summary["metric_summary"]["score"]["mean"], 0.5)
        self.assertFalse(summary["authorization_thresholds"]["thresholds_changed"])



if __name__ == "__main__":
    unittest.main()
