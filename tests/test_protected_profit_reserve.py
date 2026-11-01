import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bot.portfolio_store import SQLitePortfolioStore
from bot.virtual_portfolio import VirtualPortfolio


class ProtectedProfitReserveTests(unittest.TestCase):
    def test_seventy_percent_of_positive_realized_profit_is_protected_and_not_spendable(self):
        portfolio = VirtualPortfolio(initial_balance=10_000.0, commission_rate=0.0)
        now = datetime.now(timezone.utc)
        portfolio.buy("TEST", 10, 100.0, now)
        cash_after_buy = portfolio.cash

        trade = portfolio.sell("TEST", 10, 120.0, now, reason="test profit")

        self.assertEqual(trade.realized_pnl, 200.0)
        self.assertEqual(portfolio.protected_cash, 140.0)
        self.assertEqual(portfolio.cash, cash_after_buy + 1_060.0)
        self.assertEqual(portfolio.cash + portfolio.protected_cash, 10_200.0)
        self.assertEqual(portfolio.realized_pnl, 200.0)

    def test_losses_do_not_reduce_or_increase_protected_reserve(self):
        portfolio = VirtualPortfolio(
            initial_balance=10_000.0,
            commission_rate=0.0,
            protected_cash=75.0,
        )
        now = datetime.now(timezone.utc)
        portfolio.buy("TEST", 10, 100.0, now)
        portfolio.sell("TEST", 10, 90.0, now, reason="test loss")

        self.assertEqual(portfolio.protected_cash, 75.0)
        self.assertEqual(portfolio.realized_pnl, -100.0)

    def test_existing_account_keeps_saved_reserve_rate_when_config_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePortfolioStore(Path(directory) / "portfolio.sqlite3")
            original = VirtualPortfolio(
                initial_balance=10_000.0, profit_reserve_rate=0.7
            )
            store.save(original)

            restored = store.load_or_create(
                initial_balance=10_000.0,
                commission_rate=0.0005,
                profit_reserve_rate=0.25,
            )

            self.assertEqual(restored.profit_reserve_rate, 0.7)

    def test_new_account_uses_configured_reserve_rate(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePortfolioStore(Path(directory) / "portfolio.sqlite3")
            created = store.load_or_create(
                initial_balance=10_000.0,
                commission_rate=0.0005,
                profit_reserve_rate=0.6,
            )
            self.assertEqual(created.profit_reserve_rate, 0.6)

    def test_protected_reserve_persists_between_loads(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePortfolioStore(Path(directory) / "portfolio.sqlite3")
            portfolio = VirtualPortfolio(initial_balance=10_000.0, protected_cash=123.45)
            store.save(portfolio)

            restored = store.load_or_create(initial_balance=10_000.0, commission_rate=0.0005)

            self.assertEqual(restored.protected_cash, 123.45)
            self.assertEqual(restored.cash, 10_000.0)


if __name__ == "__main__":
    unittest.main()
