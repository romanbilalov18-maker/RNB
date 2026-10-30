from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from bot.models import VirtualPosition, VirtualTrade
from bot.virtual_portfolio import VirtualPortfolio


class SQLitePortfolioStore:
    """Persist the virtual portfolio, trade history and equity history in SQLite."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS portfolio (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    initial_balance REAL NOT NULL,
                    commission_rate REAL NOT NULL,
                    cash REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    commissions REAL NOT NULL,
                    protected_cash REAL NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS positions (
                    ticker TEXT PRIMARY KEY,
                    quantity INTEGER NOT NULL,
                    average_price REAL NOT NULL,
                    purchase_timestamp TEXT,
                    purchase_session TEXT,
                    purchase_exchange TEXT
                );

                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL,
                    commission REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    reason TEXT NOT NULL DEFAULT 'not recorded',
                    entry_price REAL
                );

                CREATE TABLE IF NOT EXISTS equity_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    equity REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS committed_cycles (
                    cycle_id TEXT PRIMARY KEY,
                    committed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS cycle_tracking_meta (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    initialized INTEGER NOT NULL CHECK (initialized IN (0, 1))
                );

                INSERT OR IGNORE INTO cycle_tracking_meta (id, initialized) VALUES (1, 0);
                """
            )
            portfolio_columns = {row["name"] for row in db.execute("PRAGMA table_info(portfolio)")}
            if "protected_cash" not in portfolio_columns:
                db.execute("ALTER TABLE portfolio ADD COLUMN protected_cash REAL NOT NULL DEFAULT 0")
            position_columns = {row["name"] for row in db.execute("PRAGMA table_info(positions)")}
            if "purchase_timestamp" not in position_columns:
                db.execute("ALTER TABLE positions ADD COLUMN purchase_timestamp TEXT")
            if "purchase_session" not in position_columns:
                db.execute("ALTER TABLE positions ADD COLUMN purchase_session TEXT")
            if "purchase_exchange" not in position_columns:
                db.execute("ALTER TABLE positions ADD COLUMN purchase_exchange TEXT")
            trade_columns = {row["name"] for row in db.execute("PRAGMA table_info(trades)")}
            if "reason" not in trade_columns:
                db.execute("ALTER TABLE trades ADD COLUMN reason TEXT NOT NULL DEFAULT 'not recorded'")
            if "entry_price" not in trade_columns:
                db.execute("ALTER TABLE trades ADD COLUMN entry_price REAL")

    def load_or_create(
        self,
        initial_balance: float,
        commission_rate: float,
    ) -> VirtualPortfolio:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM portfolio WHERE id = 1"
            ).fetchone()

            if row is None:
                # A missing singleton row is a fresh database only when every
                # dependent state table is also empty. Never silently replace a
                # damaged account with a new balance and erase orphaned history.
                dependent_tables = (
                    "positions",
                    "trades",
                    "equity_history",
                    "committed_cycles",
                )
                residual_state = {
                    table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in dependent_tables
                }
                populated = {
                    table: count
                    for table, count in residual_state.items()
                    if count
                }
                if populated:
                    raise RuntimeError(
                        "Portfolio database is inconsistent: portfolio row id=1 "
                        "is missing while dependent state remains "
                        f"({populated}); refusing to create a new portfolio."
                    )
                portfolio = VirtualPortfolio(
                    initial_balance=initial_balance,
                    commission_rate=commission_rate,
                )
                self.save(portfolio)
                return portfolio

            portfolio = VirtualPortfolio(
                initial_balance=row["initial_balance"],
                commission_rate=row["commission_rate"],
                cash=row["cash"],
                realized_pnl=row["realized_pnl"],
                commissions=row["commissions"],
                protected_cash=row["protected_cash"],
            )

            for position in db.execute("SELECT * FROM positions"):
                portfolio.positions[position["ticker"]] = VirtualPosition(
                    ticker=position["ticker"],
                    quantity=position["quantity"],
                    average_price=position["average_price"],
                    purchase_timestamp=(datetime.fromisoformat(position["purchase_timestamp"]) if position["purchase_timestamp"] else None),
                    purchase_session=position["purchase_session"],
                    purchase_exchange=position["purchase_exchange"],
                )

            for trade in db.execute("SELECT * FROM trades ORDER BY id"):
                portfolio.trades.append(
                    VirtualTrade(
                        timestamp=datetime.fromisoformat(trade["timestamp"]),
                        ticker=trade["ticker"],
                        side=trade["side"],
                        quantity=trade["quantity"],
                        price=trade["price"],
                        commission=trade["commission"],
                        realized_pnl=trade["realized_pnl"],
                        reason=trade["reason"],
                        entry_price=trade["entry_price"],
                    )
                )

            return portfolio

    def committed_cycle_ids(self) -> set[str]:
        """Return cycle IDs committed atomically with the durable portfolio."""
        with self._connect() as db:
            return {
                str(row["cycle_id"])
                for row in db.execute("SELECT cycle_id FROM committed_cycles")
            }

    def cycle_tracking_initialized(self) -> bool:
        with self._connect() as db:
            row = db.execute(
                "SELECT initialized FROM cycle_tracking_meta WHERE id=1"
            ).fetchone()
            return bool(row and row["initialized"])

    def seed_legacy_committed_cycles(self, cycle_ids: set[str]) -> None:
        """Baseline pre-protocol audit history once during migration."""
        with self._connect() as db:
            existing = db.execute("SELECT COUNT(*) FROM committed_cycles").fetchone()[0]
            if existing:
                return
            db.executemany(
                "INSERT OR IGNORE INTO committed_cycles (cycle_id, committed_at) VALUES (?, ?)",
                [(cycle_id, "legacy-baseline") for cycle_id in sorted(cycle_ids)],
            )
            db.execute("UPDATE cycle_tracking_meta SET initialized=1 WHERE id=1")
            db.commit()

    def mark_cycle_tracking_initialized(self) -> None:
        with self._connect() as db:
            db.execute("UPDATE cycle_tracking_meta SET initialized=1 WHERE id=1")
            db.commit()

    def equity_history(self) -> list[float]:
        with self._connect() as db:
            return [
                row["equity"]
                for row in db.execute(
                    "SELECT equity FROM equity_history ORDER BY id"
                )
            ]

    def save(
        self,
        portfolio: VirtualPortfolio,
        market_prices: dict[str, float] | None = None,
        *,
        cycle_id: str | None = None,
    ) -> None:
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO portfolio
                    (id, initial_balance, commission_rate, cash,
                     realized_pnl, commissions, protected_cash)
                VALUES (1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    initial_balance=excluded.initial_balance,
                    commission_rate=excluded.commission_rate,
                    cash=excluded.cash,
                    realized_pnl=excluded.realized_pnl,
                    commissions=excluded.commissions,
                    protected_cash=excluded.protected_cash
                """,
                (
                    portfolio.initial_balance,
                    portfolio.commission_rate,
                    portfolio.cash,
                    portfolio.realized_pnl,
                    portfolio.commissions,
                    portfolio.protected_cash,
                ),
            )

            db.execute("DELETE FROM positions")
            db.executemany(
                """
                INSERT INTO positions (ticker, quantity, average_price, purchase_timestamp, purchase_session, purchase_exchange)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (p.ticker, p.quantity, p.average_price,
                     p.purchase_timestamp.isoformat() if p.purchase_timestamp else None,
                     p.purchase_session, p.purchase_exchange)
                    for p in portfolio.positions.values()
                ],
            )

            db.execute("DELETE FROM trades")
            db.executemany(
                """
                INSERT INTO trades
                    (timestamp, ticker, side, quantity, price,
                     commission, realized_pnl, reason, entry_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        trade.timestamp.isoformat(),
                        trade.ticker,
                        trade.side,
                        trade.quantity,
                        trade.price,
                        trade.commission,
                        trade.realized_pnl,
                        trade.reason,
                        trade.entry_price,
                    )
                    for trade in portfolio.trades
                ],
            )

            if cycle_id is not None:
                db.execute(
                    "INSERT INTO committed_cycles (cycle_id, committed_at) VALUES (?, ?)",
                    (cycle_id, datetime.now().astimezone().isoformat()),
                )

            if market_prices is not None:
                equity, unpriced_positions = portfolio.equity_with_available_prices(
                    market_prices
                )
                if unpriced_positions:
                    # Portfolio cash/positions/trades must still commit. Do not
                    # append a misleading partial value to equity_history.
                    print(
                        "PORTFOLIO STORE: saved portfolio/trades without an equity "
                        "history point; missing fresh prices for "
                        + ", ".join(unpriced_positions)
                    )
                else:
                    db.execute(
                        "INSERT INTO equity_history (timestamp, equity) VALUES (?, ?)",
                        (datetime.now().astimezone().isoformat(), equity),
                    )

            db.commit()
