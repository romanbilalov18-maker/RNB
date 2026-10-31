"""Reconcile persisted portfolio balances and positions against the trade ledger."""

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


def _number(label: str, value: object) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PortfolioReconciliationError(f"{label} is not numeric") from exc
    if not math.isfinite(result):
        raise PortfolioReconciliationError(f"{label} is not finite")
    return result


def _assert_close(label: str, actual: float, expected: float) -> None:
    if not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-6):
        raise PortfolioReconciliationError(
            f"{label} mismatch: actual={actual:.12f} expected={expected:.12f}"
        )


def _reconcile_trade_ledger(
    *,
    initial_balance: float,
    commission_rate: float,
    reserve_rate: float,
    trades: list[sqlite3.Row],
    stored_positions: list[sqlite3.Row],
) -> tuple[float, float, float, float, int]:
    """Rebuild cash, protected reserve, realized P/L and open positions from trades."""
    expected_cash = initial_balance
    expected_reserve = 0.0
    expected_realized = 0.0
    expected_commissions = 0.0
    legacy_reserve_trade_count = 0
    positions: dict[str, dict[str, float]] = {}

    for index, trade in enumerate(trades, start=1):
        ticker = str(trade["ticker"] or "").strip()
        side = str(trade["side"] or "").upper()
        quantity_value = trade["quantity"]
        if isinstance(quantity_value, bool) or not isinstance(quantity_value, int) or quantity_value <= 0:
            raise PortfolioReconciliationError(f"trade #{index} has invalid quantity")
        quantity = quantity_value
        price = _number(f"trade #{index} price", trade["price"])
        commission = _number(f"trade #{index} commission", trade["commission"])
        recorded_pnl = _number(f"trade #{index} realized P/L", trade["realized_pnl"])
        reserve_transfer = (
            _number(f"trade #{index} reserve transfer", trade["reserve_transfer"])
            if "reserve_transfer" in trade.keys() and trade["reserve_transfer"] is not None
            else None
        )
        if not ticker or price <= 0 or commission < 0:
            raise PortfolioReconciliationError(f"trade #{index} has invalid ticker, price or commission")
        expected_commission = quantity * price * commission_rate
        _assert_close(
            f"trade #{index} commission",
            commission,
            expected_commission,
        )
        expected_commissions += commission

        if side == "BUY":
            if "entry_price" in trade.keys() and trade["entry_price"] is not None:
                recorded_entry = _number(
                    f"trade #{index} entry price", trade["entry_price"]
                )
                _assert_close(
                    f"trade #{index} BUY entry price", recorded_entry, price
                )
            expected_cash -= quantity * price + commission
            position = positions.setdefault(ticker, {"quantity": 0, "average_price": 0.0})
            old_quantity = position["quantity"]
            new_quantity = old_quantity + quantity
            position["average_price"] = (
                old_quantity * position["average_price"] + quantity * price
            ) / new_quantity
            position["quantity"] = new_quantity
            _assert_close(f"trade #{index} BUY realized P/L", recorded_pnl, 0.0)
            continue

        if side != "SELL":
            raise PortfolioReconciliationError(f"trade #{index} has unsupported side {side!r}")
        position = positions.get(ticker)
        if position is None or quantity > position["quantity"]:
            raise PortfolioReconciliationError(
                f"trade #{index} sells more {ticker} than the ledger holds"
            )
        entry_price = position["average_price"]
        if "entry_price" in trade.keys() and trade["entry_price"] is not None:
            recorded_entry = _number(
                f"trade #{index} entry price", trade["entry_price"]
            )
            _assert_close(
                f"trade #{index} SELL entry price", recorded_entry, entry_price
            )
        entry_commission = quantity * entry_price * commission_rate
        calculated_pnl = quantity * (price - entry_price) - commission - entry_commission
        _assert_close(f"trade #{index} SELL realized P/L", recorded_pnl, calculated_pnl)
        if reserve_transfer is None:
            legacy_reserve_trade_count += 1
            reserve_transfer_for_cash = 0.0
        else:
            if reserve_transfer < 0 or reserve_transfer > max(calculated_pnl, 0.0) + 1e-6:
                raise PortfolioReconciliationError(
                    f"trade #{index} reserve transfer is outside realized-profit bounds"
                )
            reserve_transfer_for_cash = reserve_transfer
            expected_reserve += reserve_transfer
        expected_cash += quantity * price - commission - reserve_transfer_for_cash
        expected_realized += calculated_pnl
        position["quantity"] -= quantity
        if position["quantity"] == 0:
            del positions[ticker]

    persisted: dict[str, tuple[int, float]] = {}
    for row in stored_positions:
        ticker = str(row["ticker"] or "").strip()
        quantity = row["quantity"]
        average_price = _number(f"position {ticker} average price", row["average_price"])
        if not ticker or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0 or average_price <= 0:
            raise PortfolioReconciliationError(f"stored position {ticker!r} is invalid")
        if ticker in persisted:
            raise PortfolioReconciliationError(f"duplicate stored position {ticker}")
        persisted[ticker] = (quantity, average_price)

    if set(persisted) != set(positions):
        missing = sorted(set(positions) - set(persisted))
        unexpected = sorted(set(persisted) - set(positions))
        raise PortfolioReconciliationError(
            f"open positions differ from trade ledger: missing={missing}, unexpected={unexpected}"
        )
    for ticker, rebuilt in positions.items():
        quantity, average_price = persisted[ticker]
        if quantity != rebuilt["quantity"]:
            raise PortfolioReconciliationError(
                f"position {ticker} quantity mismatch: actual={quantity} expected={int(rebuilt['quantity'])}"
            )
        _assert_close(
            f"position {ticker} average price",
            average_price,
            rebuilt["average_price"],
        )

    return expected_cash, expected_reserve, expected_realized, expected_commissions, legacy_reserve_trade_count


def reconcile_portfolio_databases(
    portfolio_path: str | Path,
    audit_path: str | Path,
) -> dict[str, float | int]:
    """Check account totals, open positions, trade ledger and decision audit."""
    portfolio_path = Path(portfolio_path)
    audit_path = Path(audit_path)
    if not portfolio_path.is_file() or not audit_path.is_file():
        raise PortfolioReconciliationError(
            "portfolio and decision-audit databases must both exist"
        )

    with sqlite3.connect(portfolio_path) as db:
        db.row_factory = sqlite3.Row
        _require_columns(
            db,
            "portfolio",
            {
                "id", "initial_balance", "commission_rate", "cash",
                "realized_pnl", "commissions", "protected_cash", "profit_reserve_rate",
            },
        )
        _require_columns(
            db,
            "positions",
            {"ticker", "quantity", "average_price"},
        )
        _require_columns(
            db,
            "trades",
            {"ticker", "side", "quantity", "price", "commission", "realized_pnl"},
        )
        accounts = db.execute(
            "SELECT initial_balance, commission_rate, cash, realized_pnl, "
            "commissions, protected_cash, profit_reserve_rate "
            "FROM portfolio WHERE id=1"
        ).fetchall()
        if len(accounts) != 1:
            raise PortfolioReconciliationError(
                f"expected one portfolio account row, found {len(accounts)}"
            )
        account = accounts[0]
        initial_balance = _number("initial_balance", account["initial_balance"])
        commission_rate = _number("commission_rate", account["commission_rate"])
        account_cash = _number("cash", account["cash"])
        account_realized = _number("portfolio realized P/L", account["realized_pnl"])
        account_commissions = _number("portfolio commissions", account["commissions"])
        account_reserve = _number("protected_cash", account["protected_cash"])
        reserve_rate = _number("profit_reserve_rate", account["profit_reserve_rate"])
        if initial_balance <= 0 or commission_rate < 0 or not 0 <= reserve_rate <= 1:
            raise PortfolioReconciliationError("portfolio configuration values are outside valid ranges")
        trades = db.execute("SELECT * FROM trades ORDER BY id").fetchall()
        stored_positions = db.execute(
            "SELECT ticker, quantity, average_price FROM positions ORDER BY ticker"
        ).fetchall()

    expected_cash, expected_reserve, trade_realized, trade_commissions, legacy_reserve_trade_count = (
        _reconcile_trade_ledger(
            initial_balance=initial_balance,
            commission_rate=commission_rate,
            reserve_rate=reserve_rate,
            trades=trades,
            stored_positions=stored_positions,
        )
    )

    with sqlite3.connect(audit_path) as db:
        db.row_factory = sqlite3.Row
        _require_columns(
            db,
            "decision_audit",
            {"ticker", "virtual_action", "virtual_quantity", "virtual_commission", "realized_pnl"},
        )
        audit_count, action_rows, audit_commissions, audit_realized = db.execute(
            "SELECT COUNT(*), "
            "SUM(CASE WHEN virtual_action != 'NO_TRADE' THEN 1 ELSE 0 END), "
            "COALESCE(SUM(virtual_commission), 0), "
            "COALESCE(SUM(realized_pnl), 0) FROM decision_audit"
        ).fetchone()
        audit_by_ticker = db.execute(
            "SELECT ticker, SUM(virtual_quantity) AS quantity, "
            "COALESCE(SUM(virtual_commission), 0) AS commissions, "
            "COALESCE(SUM(realized_pnl), 0) AS realized_pnl, "
            "GROUP_CONCAT(virtual_action, '+') AS actions "
            "FROM decision_audit WHERE virtual_action != 'NO_TRADE' "
            "GROUP BY ticker ORDER BY ticker"
        ).fetchall()

    ledger_by_ticker: dict[str, dict[str, float | int]] = {}
    for trade in trades:
        ticker = str(trade["ticker"] or "").strip()
        aggregate = ledger_by_ticker.setdefault(
            ticker, {
                "quantity": 0, "commissions": 0.0, "realized_pnl": 0.0,
                "BUY": 0, "SELL": 0,
            }
        )
        side = str(trade["side"] or "").upper()
        if side not in {"BUY", "SELL"}:
            raise PortfolioReconciliationError(
                f"trade for {ticker} has unsupported side {side!r}"
            )
        aggregate[side] += 1
        aggregate["quantity"] += int(trade["quantity"])
        aggregate["commissions"] += _number(
            f"trade {ticker} commission", trade["commission"]
        )
        aggregate["realized_pnl"] += _number(
            f"trade {ticker} realized P/L", trade["realized_pnl"]
        )

    audit_ticker_totals = {
        str(row["ticker"]): {
            "quantity": int(row["quantity"] or 0),
            "commissions": _number(
                f"audit {row['ticker']} commissions", row["commissions"]
            ),
            "realized_pnl": _number(
                f"audit {row['ticker']} realized P/L", row["realized_pnl"]
            ),
            "BUY": 0,
            "SELL": 0,
        }
        for row in audit_by_ticker
    }
    for row in audit_by_ticker:
        ticker = str(row["ticker"])
        actions = str(row["actions"] or "").split("+")
        for action in actions:
            if action not in {"BUY", "SELL"}:
                raise PortfolioReconciliationError(
                    f"audit {ticker} contains unsupported execution action {action!r}"
                )
            audit_ticker_totals[ticker][action] += 1
    if set(audit_ticker_totals) != set(ledger_by_ticker):
        raise PortfolioReconciliationError(
            "audit tickers differ from trade ledger: "
            f"audit={sorted(audit_ticker_totals)}, ledger={sorted(ledger_by_ticker)}"
        )
    for ticker, expected in ledger_by_ticker.items():
        actual = audit_ticker_totals[ticker]
        if actual["BUY"] != expected["BUY"] or actual["SELL"] != expected["SELL"]:
            raise PortfolioReconciliationError(
                f"audit {ticker} execution-side count mismatch: "
                f"BUY actual={actual['BUY']} expected={expected['BUY']}; "
                f"SELL actual={actual['SELL']} expected={expected['SELL']}"
            )
        if actual["quantity"] != expected["quantity"]:
            raise PortfolioReconciliationError(
                f"audit {ticker} quantity mismatch: "
                f"actual={actual['quantity']} expected={expected['quantity']}"
            )
        _assert_close(
            f"audit {ticker} commissions",
            actual["commissions"],
            expected["commissions"],
        )
        _assert_close(
            f"audit {ticker} realized P/L",
            actual["realized_pnl"],
            expected["realized_pnl"],
        )

    if legacy_reserve_trade_count:
        # Legacy sells lack per-trade reserve transfers. Reconcile conserved
        # cash + reserve and preserve the persisted aggregate reserve anchor.
        legacy_reserve = account_reserve - expected_reserve
        if legacy_reserve < -1e-6:
            raise PortfolioReconciliationError(
                "persisted protected reserve is below explicitly recorded trade transfers"
            )
        expected_cash -= max(legacy_reserve, 0.0)
        expected_reserve = account_reserve

    totals = {
        "trade_count": len(trades),
        "legacy_reserve_trades": legacy_reserve_trade_count,
        "audit_rows": int(audit_count),
        "audit_action_rows": int(action_rows or 0),
        "audit_tickers": len(audit_ticker_totals),
        "cash": account_cash,
        "protected_cash": account_reserve,
        "commissions": account_commissions,
        "realized_pnl": account_realized,
        "open_positions": len(stored_positions),
    }
    _assert_close("portfolio cash vs trade ledger", account_cash, expected_cash)
    _assert_close("portfolio protected reserve vs trade ledger", account_reserve, expected_reserve)
    _assert_close("portfolio commissions vs trade ledger", account_commissions, trade_commissions)
    _assert_close("portfolio realized P/L vs trade ledger", account_realized, trade_realized)
    _assert_close("audit commissions vs trade ledger", _number("audit commissions", audit_commissions), trade_commissions)
    _assert_close("audit realized P/L vs trade ledger", _number("audit realized P/L", audit_realized), trade_realized)
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
        return 1

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
        f"open_positions={totals['open_positions']} "
        f"cash={totals['cash']:.6f} protected_cash={totals['protected_cash']:.6f} "
        f"commissions={totals['commissions']:.6f} "
        f"realized_pnl={totals['realized_pnl']:.6f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
