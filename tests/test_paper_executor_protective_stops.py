from datetime import datetime, timedelta, timezone
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
import unittest

from bot.paper_executor import PaperExecutor
from bot.virtual_portfolio import VirtualPortfolio


class PaperExecutorProtectiveStopTests(unittest.TestCase):
    def test_trailing_stop_ratchets_up_after_current_daily_bar_protection_check(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        history = [
            SimpleNamespace(
                time=start + timedelta(days=index),
                high=102.0 + index * 0.0,
                low=99.0,
                close=101.0,
                is_complete=True,
            )
            for index in range(15)
        ]
        portfolio = VirtualPortfolio(10_000.0, commission_rate=0.0005)
        portfolio.buy("AAA", 10, 100.0, start)
        position = portfolio.positions["AAA"]
        position.initial_stop_price = 95.0
        position.stop_price = 95.0
        position.high_watermark = 100.0
        position.initial_stop_risk_per_share = (
            100.0 * 1.0005 - 95.0 * 0.9995
        )
        position.stop_model = "ATR14_X2"

        current_bar = SimpleNamespace(
            time=start + timedelta(days=15),
            open=105.0,
            high=110.0,
            low=105.0,
            close=108.0,
        )
        scan = SimpleNamespace(
            analyses={},
            buy_candidates=[],
            current_prices={"AAA": 105.0},
            previous_closes={"AAA": 101.0},
            lot_sizes={},
            active_trading_tickers={"AAA"},
            fresh_quote_tickers={"AAA"},
            sellable_quote_tickers={"AAA"},
            session_by_ticker={},
            candle_history={"AAA": history},
            market_closed_tickers=set(),
            execution_candles={"AAA": current_bar},
        )

        sells, buys = PaperExecutor(take_profit=0.50).execute(
            portfolio,
            scan,
            eligible_buy_tickers=set(),
            eligible_buy_reasons={},
            as_of=start + timedelta(days=15),
            execution_candles={"AAA": current_bar},
        )

        self.assertEqual(sells, [])
        self.assertEqual(buys, [])
        self.assertEqual(position.high_watermark, 110.0)
        self.assertAlmostEqual(position.stop_price, 104.0)
        self.assertEqual(position.stop_updated_at, start + timedelta(days=15))

    def test_persisted_stop_triggers_without_strategy_analysis(self):
        timestamp = datetime(2026, 1, 20, tzinfo=timezone.utc)
        portfolio = VirtualPortfolio(10_000.0, commission_rate=0.0005)
        portfolio.buy("AAA", 10, 100.0, timestamp)
        position = portfolio.positions["AAA"]
        position.initial_stop_price = 95.0
        position.stop_price = 97.0
        position.high_watermark = 100.0
        position.initial_stop_risk_per_share = 5.0975

        scan = SimpleNamespace(
            analyses={},
            buy_candidates=[],
            current_prices={"AAA": 96.0},
            previous_closes={"AAA": 100.0},
            lot_sizes={},
            active_trading_tickers={"AAA"},
            fresh_quote_tickers={"AAA"},
            sellable_quote_tickers={"AAA"},
            session_by_ticker={},
            candle_history={},
            market_closed_tickers=set(),
        )

        output = StringIO()
        with redirect_stdout(output):
            sells, _ = PaperExecutor().execute(
                portfolio,
                scan,
                eligible_buy_tickers=set(),
                eligible_buy_reasons={},
                as_of=timestamp + timedelta(minutes=1),
            )

        self.assertIn("STOP_EXIT_AUDIT", output.getvalue())
        self.assertIn("actual_loss=", output.getvalue())
        self.assertIn("initial_risk=", output.getvalue())
        self.assertEqual(len(sells), 1)
        self.assertEqual(sells[0].ticker, "AAA")
        self.assertIn("сохранённый защитный Stop Loss", sells[0].reason)
        self.assertNotIn("AAA", portfolio.positions)


    def test_new_position_receives_atr_stop_and_is_sized_from_that_distance(self):
        start = datetime(2026, 2, 1, tzinfo=timezone.utc)
        history = [
            SimpleNamespace(
                time=start + timedelta(days=index),
                high=100.5,
                low=99.5,
                close=100.0,
                is_complete=True,
            )
            for index in range(15)
        ]
        analysis = SimpleNamespace(
            ticker="AAA",
            volatility=0.1,
            score=0.9,
            momentum=0.1,
            trend_strength=0.1,
        )
        portfolio = VirtualPortfolio(10_000.0, commission_rate=0.0005)
        scan = SimpleNamespace(
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
            candle_history={"AAA": history},
            market_closed_tickers=set(),
        )

        _, buys = PaperExecutor(take_profit=0.50).execute(
            portfolio,
            scan,
            eligible_buy_tickers={"AAA"},
            eligible_buy_reasons={"AAA": "approved"},
            as_of=start + timedelta(days=15),
        )

        self.assertEqual(len(buys), 1)
        position = portfolio.positions["AAA"]
        self.assertEqual(position.stop_model, "ATR14_X2")
        expected_stop = 98.0
        self.assertAlmostEqual(position.initial_stop_price, expected_stop)
        self.assertAlmostEqual(position.stop_price, expected_stop)
        self.assertAlmostEqual(position.high_watermark, 100.0)
        self.assertGreater(position.initial_stop_risk_per_share, 2.0)
        self.assertLess(position.initial_stop_risk_per_share, 3.0)
        self.assertLessEqual(
            position.quantity * position.initial_stop_risk_per_share,
            100.0 + 1e-9,
        )


    def test_persisted_stop_gap_executes_at_real_open_not_stop_level(self):
        timestamp = datetime(2026, 3, 2, tzinfo=timezone.utc)
        portfolio = VirtualPortfolio(10_000.0, commission_rate=0.0005)
        portfolio.buy("GAP", 5, 100.0, timestamp)
        position = portfolio.positions["GAP"]
        position.initial_stop_price = 97.0
        position.stop_price = 97.0
        position.high_watermark = 100.0
        position.initial_stop_risk_per_share = 3.0985

        candle = SimpleNamespace(
            open=90.0, high=95.0, low=88.0, close=91.0
        )
        scan = SimpleNamespace(
            analyses={},
            buy_candidates=[],
            current_prices={"GAP": 90.0},
            previous_closes={"GAP": 100.0},
            lot_sizes={},
            active_trading_tickers={"GAP"},
            fresh_quote_tickers={"GAP"},
            sellable_quote_tickers={"GAP"},
            session_by_ticker={},
            candle_history={},
            market_closed_tickers=set(),
        )

        sells, _ = PaperExecutor().execute(
            portfolio,
            scan,
            eligible_buy_tickers=set(),
            eligible_buy_reasons={},
            as_of=timestamp + timedelta(days=1),
            execution_candles={"GAP": candle},
        )

        self.assertEqual(len(sells), 1)
        self.assertEqual(sells[0].price, 90.0)
        self.assertIn("гэп ниже", sells[0].reason)
        self.assertNotIn("GAP", portfolio.positions)


    def test_post_stop_cooldown_counts_only_verified_completed_later_sessions(self):
        start = datetime(2026, 5, 1, tzinfo=timezone.utc)
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("AAA", 1, 100.0, start)
        portfolio.sell("AAA", 1, 94.0, start + timedelta(days=1), reason="historический Stop Loss")
        history = [
            SimpleNamespace(
                time=start + timedelta(days=i), close=100.0, is_complete=True
            )
            for i in range(1, 4)
        ]
        weak = {"AAA": SimpleNamespace(momentum=0.1, trend_strength=0.1)}
        blocked = PaperExecutor._blocked_reentries(
            portfolio, weak, candle_history={"AAA": history}, cooldown_sessions=3
        )
        self.assertEqual(blocked, {"AAA"})
        history.append(SimpleNamespace(
            time=start + timedelta(days=4), close=100.0, is_complete=True
        ))
        released = PaperExecutor._blocked_reentries(
            portfolio, weak, candle_history={"AAA": history}, cooldown_sessions=3
        )
        self.assertEqual(released, set())

    def test_post_stop_cooldown_does_not_block_after_take_profit(self):
        start = datetime(2026, 5, 1, tzinfo=timezone.utc)
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("AAA", 1, 100.0, start)
        portfolio.sell("AAA", 1, 101.0, start + timedelta(days=1), reason="достигнут Take Profit")
        weak = {"AAA": SimpleNamespace(momentum=0.1, trend_strength=0.1)}
        self.assertEqual(PaperExecutor._blocked_reentries(
            portfolio, weak, candle_history={"AAA": []}, cooldown_sessions=3
        ), set())

    def test_legacy_five_percent_guard_remains_active_when_atr_stop_is_wider(self):
        timestamp = datetime(2026, 4, 1, tzinfo=timezone.utc)
        portfolio = VirtualPortfolio(10_000.0, commission_rate=0.0005)
        portfolio.buy("WIDE", 5, 100.0, timestamp)
        position = portfolio.positions["WIDE"]
        position.initial_stop_price = 90.0
        position.stop_price = 90.0
        position.high_watermark = 100.0
        position.initial_stop_risk_per_share = (
            100.0 * 1.0005 - 90.0 * 0.9995
        )

        candle = SimpleNamespace(
            open=100.0, high=101.0, low=94.0, close=96.0
        )
        scan = SimpleNamespace(
            analyses={},
            buy_candidates=[],
            current_prices={"WIDE": 100.0},
            previous_closes={"WIDE": 100.0},
            lot_sizes={},
            active_trading_tickers={"WIDE"},
            fresh_quote_tickers={"WIDE"},
            sellable_quote_tickers={"WIDE"},
            session_by_ticker={},
            candle_history={},
            market_closed_tickers=set(),
        )

        sells, _ = PaperExecutor().execute(
            portfolio,
            scan,
            eligible_buy_tickers=set(),
            eligible_buy_reasons={},
            as_of=timestamp + timedelta(days=1),
            execution_candles={"WIDE": candle},
        )

        expected_legacy_stop = (
            100.0 * 1.0005 * 0.95 / 0.9995
        )
        self.assertEqual(len(sells), 1)
        self.assertAlmostEqual(sells[0].price, expected_legacy_stop)
        self.assertIn("Stop Loss", sells[0].reason)
        self.assertNotIn("WIDE", portfolio.positions)


    def test_invalid_daily_ohlc_is_reported_without_fabricating_an_exit(self):
        timestamp = datetime(2026, 5, 1, tzinfo=timezone.utc)
        portfolio = VirtualPortfolio(10_000.0, commission_rate=0.0005)
        portfolio.buy("BADBAR", 2, 100.0, timestamp)
        position = portfolio.positions["BADBAR"]
        position.initial_stop_price = 95.0
        position.stop_price = 95.0
        position.high_watermark = 100.0
        position.initial_stop_risk_per_share = 5.0

        candle = SimpleNamespace(
            open=100.0, high=98.0, low=99.0, close=97.0
        )
        scan = SimpleNamespace(
            analyses={},
            buy_candidates=[],
            current_prices={"BADBAR": 100.0},
            previous_closes={"BADBAR": 100.0},
            lot_sizes={},
            active_trading_tickers={"BADBAR"},
            fresh_quote_tickers={"BADBAR"},
            sellable_quote_tickers={"BADBAR"},
            session_by_ticker={},
            candle_history={},
            market_closed_tickers=set(),
        )

        output = StringIO()
        with redirect_stdout(output):
            sells, _ = PaperExecutor().execute(
                portfolio,
                scan,
                eligible_buy_tickers=set(),
                eligible_buy_reasons={},
                as_of=timestamp + timedelta(days=1),
                execution_candles={"BADBAR": candle},
            )

        self.assertEqual(sells, [])
        self.assertIn("PROTECTIVE OHLC GUARD UNAVAILABLE", output.getvalue())
        self.assertIn("BADBAR", portfolio.positions)

    def test_executor_applies_net_profit_guard_to_sized_entry(self):
        start = datetime(2026, 2, 1, tzinfo=timezone.utc)
        history = [
            SimpleNamespace(time=start + timedelta(days=i), high=100.5,
                low=99.5, close=100.0, is_complete=True)
            for i in range(15)
        ]
        analysis = SimpleNamespace(ticker="AAA", volatility=0.1, score=0.9,
            momentum=0.1, trend_strength=0.1)
        portfolio = VirtualPortfolio(10_000.0, commission_rate=0.0005)
        scan = SimpleNamespace(
            analyses={"AAA": analysis}, buy_candidates=[analysis],
            current_prices={"AAA": 100.0}, previous_closes={"AAA": 99.0},
            lot_sizes={"AAA": 1}, active_trading_tickers={"AAA"},
            fresh_quote_tickers={"AAA"}, sellable_quote_tickers={"AAA"},
            liquidity_spread_pct_by_ticker={"AAA": 0.001},
            session_by_ticker={"AAA": {"session": "REGULAR", "instrument_exchange": "MOEX"}},
            candle_history={"AAA": history}, market_closed_tickers=set(),
        )
        output = StringIO()
        with redirect_stdout(output):
            sells, buys = PaperExecutor(
                take_profit=0.0015, estimated_slippage_bps=5,
                fallback_spread_pct=0.001,
            ).execute(
                portfolio, scan, eligible_buy_tickers={"AAA"},
                eligible_buy_reasons={"AAA": "approved"},
                as_of=start + timedelta(days=15),
            )
        self.assertEqual(sells, [])
        self.assertEqual(buys, [])
        self.assertEqual(portfolio.trades, [])
        self.assertIn("NET PROFIT GUARD REJECTED: ticker=AAA", output.getvalue())


if __name__ == "__main__":
    unittest.main()
