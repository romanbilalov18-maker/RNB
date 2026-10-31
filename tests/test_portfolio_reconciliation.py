import contextlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.portfolio_reconciliation import (
    PortfolioReconciliationError,
    main,
    reconcile_portfolio_databases,
)


class PortfolioReconciliationTests(unittest.TestCase):
    def _create_databases(
        self,
        directory,
        *,
        cash=842.7,
        protected_cash=9.35,
        position_quantity=15,
        position_average_price=11.0,
        account_realized=18.7,
        account_commissions=2.95,
        audit_commissions=2.95,
        audit_realized=18.7,
    ):
        portfolio_path = Path(directory) / "portfolio.sqlite3"
        audit_path = Path(directory) / "audit.sqlite3"
        with sqlite3.connect(portfolio_path) as db:
            db.executescript(
                """
                CREATE TABLE portfolio (
                    id INTEGER PRIMARY KEY, initial_balance REAL NOT NULL,
                    commission_rate REAL NOT NULL, cash REAL NOT NULL,
                    realized_pnl REAL NOT NULL, commissions REAL NOT NULL,
                    protected_cash REAL NOT NULL, profit_reserve_rate REAL NOT NULL
                );
                CREATE TABLE positions (
                    ticker TEXT PRIMARY KEY, quantity INTEGER NOT NULL,
                    average_price REAL NOT NULL
                );
                CREATE TABLE trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL,
                    side TEXT NOT NULL, quantity INTEGER NOT NULL, price REAL NOT NULL,
                    commission REAL NOT NULL, realized_pnl REAL NOT NULL
                );
                INSERT INTO trades (ticker, side, quantity, price, commission, realized_pnl)
                    VALUES ('AAA', 'BUY', 10, 10, 1.0, 0.0);
                INSERT INTO trades (ticker, side, quantity, price, commission, realized_pnl)
                    VALUES ('AAA', 'BUY', 10, 12, 1.2, 0.0);
                INSERT INTO trades (ticker, side, quantity, price, commission, realized_pnl)
                    VALUES ('AAA', 'SELL', 5, 15, 0.75, 18.7);
                """
            )
            db.execute(
                "INSERT INTO portfolio VALUES (1, 1000.0, 0.01, ?, ?, ?, ?, 0.5)",
                (cash, account_realized, account_commissions, protected_cash),
            )
            if position_quantity is not None:
                db.execute(
                    "INSERT INTO positions VALUES ('AAA', ?, ?)",
                    (position_quantity, position_average_price),
                )
        with sqlite3.connect(audit_path) as db:
            db.executescript(
                """
                CREATE TABLE decision_audit (
                    virtual_action TEXT NOT NULL,
                    virtual_commission REAL NOT NULL,
                    realized_pnl REAL NOT NULL
                );
                INSERT INTO decision_audit VALUES ('BUY', 1.0, 0.0);
                INSERT INTO decision_audit VALUES ('BUY', 1.2, 0.0);
                """
            )
            db.execute(
                "INSERT INTO decision_audit VALUES ('SELL', ?, ?)",
                (audit_commissions - 2.2, audit_realized),
            )
        return portfolio_path, audit_path


    def test_cli_fails_when_either_persisted_database_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_path = Path(directory) / "portfolio.sqlite3"
            audit_path = Path(directory) / "audit.sqlite3"
            with sqlite3.connect(portfolio_path):
                pass
            output = io.StringIO()
            with patch(
                "sys.argv",
                ["portfolio_reconciliation", "--portfolio", str(portfolio_path),
                 "--audit", str(audit_path)],
            ), contextlib.redirect_stdout(output):
                result = main()

            self.assertEqual(result, 1)
            self.assertIn("status=incomplete", output.getvalue())

    def test_accepts_matching_cash_reserve_positions_and_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_path, audit_path = self._create_databases(directory)

            result = reconcile_portfolio_databases(portfolio_path, audit_path)

            self.assertEqual(result["trade_count"], 3)
            self.assertEqual(result["audit_action_rows"], 3)
            self.assertEqual(result["open_positions"], 1)
            self.assertAlmostEqual(result["cash"], 842.7)
            self.assertAlmostEqual(result["protected_cash"], 9.35)
            self.assertAlmostEqual(result["commissions"], 2.95)
            self.assertAlmostEqual(result["realized_pnl"], 18.7)

    def test_rejects_trade_commission_mismatch_even_when_aggregates_match(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_path, audit_path = self._create_databases(
                directory,
                cash=842.8,
                account_commissions=2.85,
                audit_commissions=2.85,
            )
            with sqlite3.connect(portfolio_path) as db:
                db.execute("UPDATE trades SET commission=0.9 WHERE id=1")
            with sqlite3.connect(audit_path) as db:
                db.execute(
                    "UPDATE decision_audit SET virtual_commission=0.9 "
                    "WHERE virtual_action='BUY' AND virtual_commission=1.0"
                )
                db.execute(
                    "UPDATE decision_audit SET virtual_commission=0.75 "
                    "WHERE virtual_action='SELL'"
                )

            with self.assertRaisesRegex(PortfolioReconciliationError, "trade #1 commission"):
                reconcile_portfolio_databases(portfolio_path, audit_path)

    def test_rejects_cash_that_does_not_match_trade_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_path, audit_path = self._create_databases(directory, cash=850.0)

            with self.assertRaisesRegex(PortfolioReconciliationError, "cash vs trade ledger"):
                reconcile_portfolio_databases(portfolio_path, audit_path)

    def test_rejects_protected_reserve_that_does_not_match_profit_transfers(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_path, audit_path = self._create_databases(directory, protected_cash=8.0)

            with self.assertRaisesRegex(PortfolioReconciliationError, "protected reserve"):
                reconcile_portfolio_databases(portfolio_path, audit_path)

    def test_rejects_open_position_quantity_that_differs_from_trade_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_path, audit_path = self._create_databases(
                directory, position_quantity=14
            )

            with self.assertRaisesRegex(PortfolioReconciliationError, "quantity mismatch"):
                reconcile_portfolio_databases(portfolio_path, audit_path)

    def test_rejects_open_position_average_price_that_differs_from_trade_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_path, audit_path = self._create_databases(
                directory, position_average_price=10.5
            )

            with self.assertRaisesRegex(PortfolioReconciliationError, "average price"):
                reconcile_portfolio_databases(portfolio_path, audit_path)

    def test_rejects_sell_realized_pnl_that_does_not_match_entry_cost_and_fees(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_path, audit_path = self._create_databases(directory)
            with sqlite3.connect(portfolio_path) as db:
                db.execute("UPDATE trades SET realized_pnl=19.0 WHERE side='SELL'")

            with self.assertRaisesRegex(PortfolioReconciliationError, "SELL realized P/L"):
                reconcile_portfolio_databases(portfolio_path, audit_path)

    def test_rejects_audit_commission_total_that_differs_from_trade_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_path, audit_path = self._create_databases(
                directory, audit_commissions=3.0
            )

            with self.assertRaisesRegex(PortfolioReconciliationError, "audit commissions"):
                reconcile_portfolio_databases(portfolio_path, audit_path)

    def test_rejects_account_aggregate_that_differs_from_trade_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_path, audit_path = self._create_databases(
                directory, account_commissions=3.1
            )

            with self.assertRaisesRegex(PortfolioReconciliationError, "portfolio commissions"):
                reconcile_portfolio_databases(portfolio_path, audit_path)


if __name__ == "__main__":
    unittest.main()
