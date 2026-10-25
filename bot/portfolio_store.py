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
                    average_price REAL NOT NULL
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
                """
            )
            portfolio_columns = {row["name"] for row in db.execute("PRAGMA table_info(portfolio)")}
            if "protected_cash" not in portfolio_columns:
                db.execute("ALTER TABLE portfolio ADD COLUMN protected_cash REAL NOT NULL DEFAULT 0")
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
                INSERT INTO positions (ticker, quantity, average_price)
                VALUES (?, ?, ?)
                """,
                [
                    (p.ticker, p.quantity, p.average_price)
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
