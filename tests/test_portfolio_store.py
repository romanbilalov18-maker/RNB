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

    def test_new_store_creates_initial_portfolio(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePortfolioStore(Path(directory) / "portfolio.sqlite3")

            portfolio = store.load_or_create(10_000, 0.001)

            self.assertEqual(portfolio.cash, 10_000)
            self.assertEqual(portfolio.positions, {})
            self.assertEqual(portfolio.trades, [])


if __name__ == "__main__":
    unittest.main()
