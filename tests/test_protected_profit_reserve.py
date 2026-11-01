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

    def test_buy_cannot_spend_protected_cash_when_trading_cash_is_insufficient(self):
        portfolio = VirtualPortfolio(
            initial_balance=1_000.0,
            commission_rate=0.0,
            cash=50.0,
            protected_cash=100.0,
        )

        with self.assertRaisesRegex(ValueError, "insufficient virtual cash"):
            portfolio.buy("TEST", 6, 10.0, datetime.now(timezone.utc))

        self.assertEqual(portfolio.cash, 50.0)
        self.assertEqual(portfolio.protected_cash, 100.0)
        self.assertEqual(portfolio.positions, {})
        self.assertEqual(portfolio.trades, [])

    def test_reserve_accumulates_across_wins_survives_loss_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePortfolioStore(Path(directory) / "portfolio.sqlite3")
            portfolio = VirtualPortfolio(
                initial_balance=1_000.0,
                commission_rate=0.0,
                profit_reserve_rate=0.7,
            )
            now = datetime.now(timezone.utc)

            portfolio.buy("WIN1", 10, 10.0, now)
            first_win = portfolio.sell("WIN1", 10, 12.0, now, reason="first win")
            self.assertEqual(first_win.reserve_transfer, 14.0)

            portfolio.buy("WIN2", 10, 10.0, now)
            second_win = portfolio.sell("WIN2", 10, 13.0, now, reason="second win")
            self.assertEqual(second_win.reserve_transfer, 21.0)
            self.assertEqual(portfolio.protected_cash, 35.0)

            portfolio.buy("LOSS", 10, 10.0, now)
            losing_trade = portfolio.sell("LOSS", 10, 9.0, now, reason="loss")
            self.assertEqual(losing_trade.reserve_transfer, 0.0)
            self.assertEqual(portfolio.protected_cash, 35.0)

            store.save(portfolio)
            restored = store.load_or_create(1_000.0, 0.0)

            self.assertEqual(restored.protected_cash, 35.0)
            self.assertEqual(restored.cash, portfolio.cash)
            self.assertEqual(
                [trade.reserve_transfer for trade in restored.trades if trade.side == "SELL"],
                [14.0, 21.0, 0.0],
            )

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
