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

    def test_position_performance_includes_exit_commission(self):
        portfolio = VirtualPortfolio(10_000, commission_rate=0.001)
        timestamp = datetime.now(timezone.utc)
        portfolio.buy("TEST", 10, 100, timestamp)

        performance = portfolio.position_performance({"TEST": 110})[0]

        self.assertAlmostEqual(performance.invested_value, 1_000.0)
        self.assertAlmostEqual(performance.current_value, 1_100.0)
        self.assertAlmostEqual(performance.unrealized_pnl, 100.0)
        self.assertAlmostEqual(performance.unrealized_return_pct, 10.0)
        self.assertAlmostEqual(performance.estimated_sell_commission, 1.1)
        self.assertAlmostEqual(performance.net_if_sold_now, 98.9)
        self.assertAlmostEqual(performance.net_return_pct_if_sold_now, 9.89)


if __name__ == "__main__":
    unittest.main()
