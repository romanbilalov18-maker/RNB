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
                    commissions REAL NOT NULL
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
                    realized_pnl REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS equity_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    equity REAL NOT NULL
                );
                """
            )

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
                    )
                )

            return portfolio

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
    ) -> None:
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO portfolio
                    (id, initial_balance, commission_rate, cash,
                     realized_pnl, commissions)
                VALUES (1, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    initial_balance=excluded.initial_balance,
                    commission_rate=excluded.commission_rate,
                    cash=excluded.cash,
                    realized_pnl=excluded.realized_pnl,
                    commissions=excluded.commissions
                """,
                (
                    portfolio.initial_balance,
                    portfolio.commission_rate,
                    portfolio.cash,
                    portfolio.realized_pnl,
                    portfolio.commissions,
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
                     commission, realized_pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?)
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
                    )
                    for trade in portfolio.trades
                ],
            )

            if market_prices is not None:
                equity = portfolio.equity(market_prices)
                db.execute(
                    "INSERT INTO equity_history (timestamp, equity) VALUES (?, ?)",
                    (datetime.now().astimezone().isoformat(), equity),
                )

            db.commit()
