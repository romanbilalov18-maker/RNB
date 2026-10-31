"""Reconcile persisted portfolio totals against trades and decision audit."""

from __future__ import annotations

import argparse
import math
import sqlite3
from pathlib import Path


class PortfolioReconciliationError(RuntimeError):
    """Raised when financial totals disagree across persisted portfolio data."""


def _require_columns(db: sqlite3.Connection, table: str, required: set[str]) -> None:
    tables = {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if table not in tables:
        raise PortfolioReconciliationError(f"required table is missing: {table}")
    columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
    missing = required - columns
    if missing:
        raise PortfolioReconciliationError(
            f"{table} is missing required columns: {', '.join(sorted(missing))}"
        )


def _assert_close(label: str, actual: float, expected: float) -> None:
    if not math.isfinite(actual) or not math.isfinite(expected):
        raise PortfolioReconciliationError(f"{label} is not finite")
    if not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-6):
        raise PortfolioReconciliationError(
            f"{label} mismatch: actual={actual:.12f} expected={expected:.12f}"
        )


def reconcile_portfolio_databases(
    portfolio_path: str | Path,
    audit_path: str | Path,
) -> dict[str, float | int]:
    """Check account totals against the trade ledger and decision audit totals.

    The audit stores one row per ticker and cycle, so action-row counts are
    diagnostic only. Money totals are the cross-database reconciliation keys.
    """
    portfolio_path = Path(portfolio_path)
    audit_path = Path(audit_path)
    if not portfolio_path.is_file() or not audit_path.is_file():
        raise PortfolioReconciliationError(
            "portfolio and decision-audit databases must both exist"
        )

    with sqlite3.connect(portfolio_path) as db:
        _require_columns(
            db,
            "portfolio",
            {"id", "realized_pnl", "commissions", "cash"},
        )
        _require_columns(db, "trades", {"commission", "realized_pnl"})
        accounts = db.execute(
            "SELECT realized_pnl, commissions, cash FROM portfolio WHERE id=1"
        ).fetchall()
        if len(accounts) != 1:
            raise PortfolioReconciliationError(
                f"expected one portfolio account row, found {len(accounts)}"
            )
        account_realized, account_commissions, cash = map(float, accounts[0])
        trade_count, trade_commissions, trade_realized = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(commission), 0), "
            "COALESCE(SUM(realized_pnl), 0) FROM trades"
        ).fetchone()

    with sqlite3.connect(audit_path) as db:
        _require_columns(
            db,
            "decision_audit",
            {"virtual_action", "virtual_commission", "realized_pnl"},
        )
        audit_count, action_rows, audit_commissions, audit_realized = db.execute(
            "SELECT COUNT(*), "
            "SUM(CASE WHEN virtual_action != 'NO_TRADE' THEN 1 ELSE 0 END), "
            "COALESCE(SUM(virtual_commission), 0), "
            "COALESCE(SUM(realized_pnl), 0) FROM decision_audit"
        ).fetchone()

    totals = {
        "trade_count": int(trade_count),
        "audit_rows": int(audit_count),
        "audit_action_rows": int(action_rows or 0),
        "commissions": float(account_commissions),
        "realized_pnl": float(account_realized),
        "cash": float(cash),
    }
    _assert_close("portfolio commissions vs trade ledger", totals["commissions"], float(trade_commissions))
    _assert_close("portfolio realized P/L vs trade ledger", totals["realized_pnl"], float(trade_realized))
    _assert_close("audit commissions vs trade ledger", float(audit_commissions), float(trade_commissions))
    _assert_close("audit realized P/L vs trade ledger", float(audit_realized), float(trade_realized))
    return totals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portfolio", required=True, type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    args = parser.parse_args()

    if not args.portfolio.is_file() or not args.audit.is_file():
        print(
            "RECONCILIATION status=incomplete "
            f"portfolio_exists={args.portfolio.is_file()} audit_exists={args.audit.is_file()}"
        )
        return 0

    try:
        totals = reconcile_portfolio_databases(args.portfolio, args.audit)
    except (PortfolioReconciliationError, sqlite3.Error) as exc:
        print(f"RECONCILIATION status=failed reason={exc}")
        return 1

    print(
        "RECONCILIATION status=ok "
        f"portfolio_trade_count={totals['trade_count']} "
        f"audit_rows={totals['audit_rows']} "
        f"audit_action_rows={totals['audit_action_rows']} "
        f"commissions={totals['commissions']:.6f} "
        f"realized_pnl={totals['realized_pnl']:.6f} cash={totals['cash']:.6f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
