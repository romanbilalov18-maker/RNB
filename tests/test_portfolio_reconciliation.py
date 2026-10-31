import sqlite3
import tempfile
import unittest
from pathlib import Path

from bot.portfolio_reconciliation import (
    PortfolioReconciliationError,
    reconcile_portfolio_databases,
)


class PortfolioReconciliationTests(unittest.TestCase):
    def _create_databases(self, directory, *, account_commissions=1.5, audit_commissions=1.5):
        portfolio_path = Path(directory) / "portfolio.sqlite3"
        audit_path = Path(directory) / "audit.sqlite3"
        with sqlite3.connect(portfolio_path) as db:
            db.executescript(
                """
                CREATE TABLE portfolio (
                    id INTEGER PRIMARY KEY, realized_pnl REAL NOT NULL,
                    commissions REAL NOT NULL, cash REAL NOT NULL
                );
                CREATE TABLE trades (
                    commission REAL NOT NULL, realized_pnl REAL NOT NULL
                );
                INSERT INTO trades VALUES (1.0, 0.0);
                INSERT INTO trades VALUES (0.5, 12.25);
                """
            )
            db.execute(
                "INSERT INTO portfolio VALUES (1, 12.25, ?, 900.0)",
                (account_commissions,),
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
                """
            )
            db.execute(
                "INSERT INTO decision_audit VALUES ('SELL', ?, 12.25)",
                (audit_commissions - 1.0,),
            )
        return portfolio_path, audit_path

    def test_accepts_matching_trade_ledger_and_audit_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_path, audit_path = self._create_databases(directory)

            result = reconcile_portfolio_databases(portfolio_path, audit_path)

            self.assertEqual(result["trade_count"], 2)
            self.assertEqual(result["audit_action_rows"], 2)
            self.assertAlmostEqual(result["commissions"], 1.5)
            self.assertAlmostEqual(result["realized_pnl"], 12.25)

    def test_rejects_commission_total_that_differs_between_portfolio_and_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_path, audit_path = self._create_databases(
                directory, audit_commissions=1.7
            )

            with self.assertRaisesRegex(PortfolioReconciliationError, "audit commissions"):
                reconcile_portfolio_databases(portfolio_path, audit_path)

    def test_rejects_account_aggregate_that_differs_from_trade_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_path, audit_path = self._create_databases(
                directory, account_commissions=2.0
            )

            with self.assertRaisesRegex(PortfolioReconciliationError, "trade ledger"):
                reconcile_portfolio_databases(portfolio_path, audit_path)


if __name__ == "__main__":
    unittest.main()
