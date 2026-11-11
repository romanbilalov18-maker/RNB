from datetime import datetime, timedelta, timezone
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
            open=100.0,
            high=110.0,
            low=99.0,
            close=108.0,
        )
        scan = SimpleNamespace(
            analyses={},
            buy_candidates=[],
            current_prices={"AAA": 100.0},
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

        sells, _ = PaperExecutor().execute(
            portfolio,
            scan,
            eligible_buy_tickers=set(),
            eligible_buy_reasons={},
            as_of=timestamp + timedelta(minutes=1),
        )

        self.assertEqual(len(sells), 1)
        self.assertEqual(sells[0].ticker, "AAA")
        self.assertIn("сохранённый защитный Stop Loss", sells[0].reason)
        self.assertNotIn("AAA", portfolio.positions)


if __name__ == "__main__":
    unittest.main()


    def test_new_position_receives_atr_stop_and_is_sized_from_that_distance(self):
        start = datetime(2026, 2, 1, tzinfo=timezone.utc)
        history = [
            SimpleNamespace(
                time=start + timedelta(days=index),
                high=102.0,
                low=99.0,
                close=101.0,
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
        self.assertAlmostEqual(position.initial_stop_price, 94.0)
        self.assertAlmostEqual(position.stop_price, 94.0)
        self.assertAlmostEqual(position.high_watermark, 100.0)
        self.assertGreater(position.initial_stop_risk_per_share, 6.0)
        self.assertLessEqual(
            position.quantity * position.initial_stop_risk_per_share,
            100.0 + 1e-9,
        )
