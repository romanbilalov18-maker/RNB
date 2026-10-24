import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bot.portfolio_store import SQLitePortfolioStore
from bot.virtual_portfolio import VirtualPortfolio


class TestSQLitePortfolioStore(unittest.TestCase):
    def test_round_trip_preserves_portfolio_and_trades(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            store = SQLitePortfolioStore(path)

            portfolio = VirtualPortfolio(10_000, commission_rate=0.001)
            timestamp = datetime.now(timezone.utc)
            portfolio.buy("TEST", 10, 100, timestamp)
            store.save(portfolio)

            restored = store.load_or_create(20_000, 0.002)

            self.assertEqual(restored.initial_balance, 10_000)
            self.assertEqual(restored.commission_rate, 0.001)
            self.assertAlmostEqual(restored.cash, 8_999)
            self.assertEqual(restored.positions["TEST"].quantity, 10)
            self.assertEqual(restored.positions["TEST"].average_price, 100)
            self.assertEqual(len(restored.trades), 1)
            self.assertEqual(restored.trades[0].ticker, "TEST")

    def test_equity_history_tracks_market_revaluation_across_saves(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePortfolioStore(Path(directory) / "portfolio.sqlite3")
            portfolio = VirtualPortfolio(10_000, commission_rate=0.001)
            portfolio.buy("TEST", 10, 100, datetime.now(timezone.utc))

            store.save(portfolio, {"TEST": 100})
            store.save(portfolio, {"TEST": 120})

            history = store.equity_history()
            self.assertEqual(len(history), 2)
            self.assertAlmostEqual(history[0], 9_999.0)
            self.assertAlmostEqual(history[1], 10_199.0)

            restored = store.load_or_create(20_000, 0.002)
            self.assertAlmostEqual(restored.equity({"TEST": 120}), 10_199.0)
            self.assertEqual(len(restored.trades), 1)
            self.assertEqual(restored.positions["TEST"].quantity, 10)

    def test_drawdown_uses_equity_history_across_store_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            store = SQLitePortfolioStore(path)
            portfolio = VirtualPortfolio(10_000, commission_rate=0.001)
            portfolio.buy("TEST", 10, 100, datetime.now(timezone.utc))

            store.save(portfolio, {"TEST": 100})
            store.save(portfolio, {"TEST": 80})

            # Simulate a process restart by constructing a new store instance.
            restarted_store = SQLitePortfolioStore(path)
            restored = restarted_store.load_or_create(10_000, 0.001)
            restarted_store.save(restored, {"TEST": 90})

            history = restarted_store.equity_history()
            current_equity = restored.equity({"TEST": 90})
            stats = restored.statistics(current_equity, history)

            self.assertEqual(len(history), 3)
            self.assertAlmostEqual(history[0], 9_999.0)
            self.assertAlmostEqual(history[1], 9_799.0)
            self.assertAlmostEqual(history[2], 9_899.0)
            self.assertAlmostEqual(stats.peak_equity, 9_999.0)
            self.assertAlmostEqual(stats.max_drawdown, 200.0)
            self.assertAlmostEqual(stats.max_drawdown_pct, 200.0 / 9_999.0 * 100.0)

    def test_missing_market_price_saves_portfolio_without_partial_equity_history(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePortfolioStore(Path(directory) / "portfolio.sqlite3")
            portfolio = VirtualPortfolio(10_000)
            portfolio.buy("TEST", 1, 100, datetime.now(timezone.utc))
            store.save(portfolio, {"TEST": 100})
            history_before = store.equity_history()

            portfolio.buy("OTHER", 1, 50, datetime.now(timezone.utc))
            store.save(portfolio, {})

            self.assertEqual(store.equity_history(), history_before)
            restored = store.load_or_create(10_000, 0.0005)
            self.assertEqual(restored.positions["TEST"].quantity, 1)
            self.assertEqual(restored.positions["OTHER"].quantity, 1)
            self.assertEqual(len(restored.trades), 2)

    def test_round_trip_preserves_protected_profit_reserve(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            store = SQLitePortfolioStore(path)
            portfolio = VirtualPortfolio(10_000, commission_rate=0.001)
            portfolio.protected_cash = 350.75
            portfolio.cash = 8_500.25
            portfolio.realized_pnl = 1_000.0
            store.save(portfolio)

            restored = SQLitePortfolioStore(path).load_or_create(
                initial_balance=20_000,
                commission_rate=0.002,
            )

            self.assertEqual(restored.initial_balance, 10_000)
            self.assertAlmostEqual(restored.protected_cash, 350.75)
            self.assertAlmostEqual(restored.cash, 8_500.25)
            self.assertAlmostEqual(restored.realized_pnl, 1_000.0)

    def test_new_store_creates_initial_portfolio(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePortfolioStore(Path(directory) / "portfolio.sqlite3")

            portfolio = store.load_or_create(10_000, 0.001)

            self.assertEqual(portfolio.cash, 10_000)
            self.assertEqual(portfolio.positions, {})
            self.assertEqual(portfolio.trades, [])


if __name__ == "__main__":
    unittest.main()
