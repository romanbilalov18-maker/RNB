import unittest
from datetime import datetime, timezone

from bot.virtual_portfolio import VirtualPortfolio


class TestVirtualPortfolio(unittest.TestCase):
    def test_buy_and_sell_with_commission(self):
        timestamp = datetime.now(timezone.utc)
        portfolio = VirtualPortfolio(10_000, commission_rate=0.001)

        portfolio.buy("TEST", 10, 100, timestamp)
        self.assertAlmostEqual(portfolio.cash, 8_999.0)
        self.assertEqual(portfolio.positions["TEST"].quantity, 10)

        trade = portfolio.sell("TEST", 10, 110, timestamp)
        self.assertAlmostEqual(trade.realized_pnl, 98.9)
        self.assertAlmostEqual(portfolio.realized_pnl, 98.9)
        self.assertEqual(portfolio.positions, {})

    def test_buy_rejects_insufficient_cash(self):
        portfolio = VirtualPortfolio(100)
        with self.assertRaises(ValueError):
            portfolio.buy("TEST", 2, 100, datetime.now(timezone.utc))

    def test_sell_rejects_missing_position(self):
        portfolio = VirtualPortfolio(10_000)
        with self.assertRaises(ValueError):
            portfolio.sell("TEST", 1, 100, datetime.now(timezone.utc))

    def test_equity_uses_current_market_prices(self):
        portfolio = VirtualPortfolio(10_000)
        timestamp = datetime.now(timezone.utc)
        portfolio.buy("TEST", 10, 100, timestamp)

        equity = portfolio.equity({"TEST": 120})
        self.assertAlmostEqual(equity, 10_199.5)


if __name__ == "__main__":
    unittest.main()
