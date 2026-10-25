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
        self.assertAlmostEqual(trade.realized_pnl, 97.9)
        self.assertAlmostEqual(portfolio.realized_pnl, 97.9)
        self.assertEqual(portfolio.positions, {})

    def test_partial_sale_allocates_entry_commission_and_reserve_consistently(self):
        timestamp = datetime(2026, 10, 20, tzinfo=timezone.utc)
        portfolio = VirtualPortfolio(10_000, commission_rate=0.001, profit_reserve_rate=0.7)

        portfolio.buy("TEST", 10, 100.0, timestamp)
        trade = portfolio.sell("TEST", 4, 110.0, timestamp)

        self.assertEqual(portfolio.positions["TEST"].quantity, 6)
        self.assertAlmostEqual(portfolio.positions["TEST"].average_price, 100.0)
        self.assertAlmostEqual(trade.commission, 0.44)
        self.assertAlmostEqual(trade.realized_pnl, 39.16)
        self.assertAlmostEqual(portfolio.realized_pnl, 39.16)
        self.assertAlmostEqual(portfolio.commissions, 1.44)
        self.assertAlmostEqual(portfolio.protected_cash, 27.412)
        self.assertAlmostEqual(portfolio.cash, 9411.148)
        self.assertAlmostEqual(portfolio.equity({"TEST": 110.0}), 10098.56)
    def test_buy_and_sell_reject_non_finite_or_boolean_prices_without_mutating_state(self):
        invalid_prices = (float("nan"), float("inf"), float("-inf"), True, False, 0, -1)
        for price in invalid_prices:
            with self.subTest(price=price):
                portfolio = VirtualPortfolio(10_000, commission_rate=0.001)
                before = (portfolio.cash, dict(portfolio.positions), list(portfolio.trades), portfolio.commissions)
                with self.assertRaisesRegex(ValueError, "finite positive number"):
                    portfolio.buy("TEST", 1, price, datetime.now(timezone.utc))
                self.assertEqual(
                    (portfolio.cash, portfolio.positions, portfolio.trades, portfolio.commissions),
                    before,
                )

                portfolio.buy("TEST", 1, 100, datetime.now(timezone.utc))
                before_sell = (
                    portfolio.cash,
                    dict(portfolio.positions),
                    list(portfolio.trades),
                    portfolio.commissions,
                    portfolio.realized_pnl,
                )
                with self.assertRaisesRegex(ValueError, "finite positive number"):
                    portfolio.sell("TEST", 1, price, datetime.now(timezone.utc))
                self.assertEqual(
                    (
                        portfolio.cash,
                        portfolio.positions,
                        portfolio.trades,
                        portfolio.commissions,
                        portfolio.realized_pnl,
                    ),
                    before_sell,
                )

    def test_quantity_must_be_a_positive_integer_and_not_bool(self):
        for quantity in (True, False, 1.5, 0, -1):
            with self.subTest(quantity=quantity):
                portfolio = VirtualPortfolio(10_000)
                with self.assertRaisesRegex(ValueError, "positive integer"):
                    portfolio.buy("TEST", quantity, 100, datetime.now(timezone.utc))
                self.assertEqual(portfolio.trades, [])
                self.assertEqual(portfolio.positions, {})

    def test_buy_rejects_insufficient_cash(self):
        portfolio = VirtualPortfolio(100)
        with self.assertRaises(ValueError):
            portfolio.buy("TEST", 2, 100, datetime.now(timezone.utc))

    def test_buy_cannot_spend_protected_profit_reserve(self):
        portfolio = VirtualPortfolio(
            initial_balance=1_000,
            commission_rate=0.001,
            cash=100.0,
            protected_cash=500.0,
        )

        with self.assertRaisesRegex(ValueError, "insufficient virtual cash"):
            portfolio.buy("TEST", 2, 50.0, datetime.now(timezone.utc))

        self.assertAlmostEqual(portfolio.cash, 100.0)
        self.assertAlmostEqual(portfolio.protected_cash, 500.0)
        self.assertEqual(portfolio.positions, {})
        self.assertEqual(portfolio.trades, [])

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

    def test_partial_equity_excludes_unpriced_positions_without_fabricating_price(self):
        portfolio = VirtualPortfolio(10_000)
        timestamp = datetime.now(timezone.utc)
        portfolio.buy("PRICED", 2, 100, timestamp)
        portfolio.buy("UNPRICED", 3, 50, timestamp)

        value, missing = portfolio.equity_with_available_prices({"PRICED": 120})

        self.assertAlmostEqual(value, portfolio.cash + 240)
        self.assertEqual(missing, ("UNPRICED",))
        with self.assertRaisesRegex(ValueError, "UNPRICED"):
            portfolio.equity({"PRICED": 120})

    def test_statistics_counts_trades_and_drawdown(self):
        portfolio = VirtualPortfolio(10_000, commission_rate=0.001)
        timestamp = datetime.now(timezone.utc)
        portfolio.buy("TEST", 10, 100, timestamp)
        portfolio.sell("TEST", 10, 110, timestamp)

        stats = portfolio.statistics(
            current_equity=10_097.9,
            equity_history=[10_000.0, 9_500.0, 10_097.9],
        )

        self.assertEqual(stats.total_trades, 2)
        self.assertEqual(stats.buy_trades, 1)
        self.assertEqual(stats.sell_trades, 1)
        self.assertEqual(stats.profitable_trades, 1)
        self.assertEqual(stats.losing_trades, 0)
        self.assertAlmostEqual(stats.win_rate_pct, 100.0)
        self.assertAlmostEqual(stats.best_realized_trade, 97.9)
        self.assertAlmostEqual(stats.worst_realized_trade, 97.9)
        self.assertAlmostEqual(stats.average_profitable_trade, 97.9)
        self.assertAlmostEqual(stats.average_losing_trade, 0.0)
        self.assertAlmostEqual(stats.max_drawdown, 500.0)
        self.assertAlmostEqual(stats.max_drawdown_pct, 5.0)

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
        self.assertAlmostEqual(performance.net_if_sold_now, 97.9)
        self.assertAlmostEqual(performance.net_return_pct_if_sold_now, 9.79)


if __name__ == "__main__":
    unittest.main()
