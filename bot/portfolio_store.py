from __future__ import annotations

import math
import sqlite3
from datetime import datetime
from pathlib import Path

from bot.models import VirtualPosition, VirtualTrade
from bot.virtual_portfolio import VirtualPortfolio



def _parse_persisted_timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"corrupt portfolio data: invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"corrupt portfolio data: {field} must include a timezone")
    return parsed


def _validate_persisted_number(value, field: str, *, positive: bool = False) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or (value <= 0 if positive else value < 0)
    ):
        qualifier = "positive finite" if positive else "finite non-negative"
        raise ValueError(f"corrupt portfolio data: {field} must be {qualifier}")
    return float(value)


def _validate_persisted_quantity(value, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"corrupt portfolio data: {field} must be a positive integer")
    return value


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
                    protected_cash REAL NOT NULL DEFAULT 0,
                    profit_reserve_rate REAL NOT NULL DEFAULT 0.7
                );

                CREATE TABLE IF NOT EXISTS positions (
                    ticker TEXT PRIMARY KEY,
                    quantity INTEGER NOT NULL,
                    average_price REAL NOT NULL,
                    purchase_timestamp TEXT,
                    purchase_session TEXT,
                    purchase_exchange TEXT,
                    quote_unavailable_cycles INTEGER NOT NULL DEFAULT 0,
                    stagnant_sessions INTEGER NOT NULL DEFAULT 0,
                    last_health_status TEXT,
                    last_health_candle_timestamp TEXT
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
            if "profit_reserve_rate" not in portfolio_columns:
                db.execute("ALTER TABLE portfolio ADD COLUMN profit_reserve_rate REAL NOT NULL DEFAULT 0.7")
            position_columns = {row["name"] for row in db.execute("PRAGMA table_info(positions)")}
            if "purchase_timestamp" not in position_columns:
                db.execute("ALTER TABLE positions ADD COLUMN purchase_timestamp TEXT")
            if "purchase_session" not in position_columns:
                db.execute("ALTER TABLE positions ADD COLUMN purchase_session TEXT")
            if "purchase_exchange" not in position_columns:
                db.execute("ALTER TABLE positions ADD COLUMN purchase_exchange TEXT")
            if "quote_unavailable_cycles" not in position_columns:
                db.execute("ALTER TABLE positions ADD COLUMN quote_unavailable_cycles INTEGER NOT NULL DEFAULT 0")
            if "stagnant_sessions" not in position_columns:
                db.execute("ALTER TABLE positions ADD COLUMN stagnant_sessions INTEGER NOT NULL DEFAULT 0")
            if "last_health_status" not in position_columns:
                db.execute("ALTER TABLE positions ADD COLUMN last_health_status TEXT")
            if "last_health_candle_timestamp" not in position_columns:
                db.execute("ALTER TABLE positions ADD COLUMN last_health_candle_timestamp TEXT")
            trade_columns = {row["name"] for row in db.execute("PRAGMA table_info(trades)")}
            if "reason" not in trade_columns:
                db.execute("ALTER TABLE trades ADD COLUMN reason TEXT NOT NULL DEFAULT 'not recorded'")
            if "entry_price" not in trade_columns:
                db.execute("ALTER TABLE trades ADD COLUMN entry_price REAL")

    def load_or_create(
        self,
        initial_balance: float,
        commission_rate: float,
        profit_reserve_rate: float = 0.7,
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
                    profit_reserve_rate=profit_reserve_rate,
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
                profit_reserve_rate=row["profit_reserve_rate"],
            )

            for position in db.execute("SELECT * FROM positions"):
                portfolio.positions[position["ticker"]] = VirtualPosition(
                    ticker=position["ticker"],
                    quantity=position["quantity"],
                    average_price=position["average_price"],
                    purchase_timestamp=(
                        _parse_persisted_timestamp(
                            position["purchase_timestamp"], "position purchase_timestamp"
                        )
                        if position["purchase_timestamp"] else None
                    ),
                    purchase_session=position["purchase_session"],
                    purchase_exchange=position["purchase_exchange"],
                    quote_unavailable_cycles=position["quote_unavailable_cycles"],
                    stagnant_sessions=position["stagnant_sessions"],
                    last_health_status=position["last_health_status"],
                    last_health_candle_timestamp=position["last_health_candle_timestamp"],
                )
                if not isinstance(position["ticker"], str) or not position["ticker"].strip():
                    raise ValueError("corrupt portfolio data: position ticker must not be empty")
                _validate_persisted_quantity(
                    position["quantity"], f"position {position['ticker']} quantity"
                )
                _validate_persisted_number(
                    position["average_price"],
                    f"position {position['ticker']} average_price",
                    positive=True,
                )
                for counter_name in ("quote_unavailable_cycles", "stagnant_sessions"):
                    counter = position[counter_name]
                    if isinstance(counter, bool) or not isinstance(counter, int) or counter < 0:
                        raise ValueError(
                            f"corrupt portfolio data: position {position['ticker']} "
                            f"{counter_name} must be a non-negative integer"
                        )

            for trade in db.execute("SELECT * FROM trades ORDER BY id"):
                if not isinstance(trade["ticker"], str) or not trade["ticker"].strip():
                    raise ValueError("corrupt portfolio data: trade ticker must not be empty")
                if trade["side"] not in {"BUY", "SELL"}:
                    raise ValueError(
                        f"corrupt portfolio data: trade {trade['id']} has invalid side"
                    )
                _validate_persisted_quantity(
                    trade["quantity"], f"trade {trade['id']} quantity"
                )
                _validate_persisted_number(
                    trade["price"], f"trade {trade['id']} price", positive=True
                )
                _validate_persisted_number(
                    trade["commission"], f"trade {trade['id']} commission"
                )
                if trade["side"] == "BUY" and trade["realized_pnl"] != 0:
                    raise ValueError(
                        f"corrupt portfolio data: BUY trade {trade['id']} has realized P/L"
                    )
                _validate_persisted_number(
                    trade["realized_pnl"], f"trade {trade['id']} realized_pnl"
                )
                if trade["entry_price"] is not None:
                    _validate_persisted_number(
                        trade["entry_price"],
                        f"trade {trade['id']} entry_price",
                        positive=True,
                    )
                portfolio.trades.append(
                    VirtualTrade(
                        timestamp=_parse_persisted_timestamp(
                            trade["timestamp"], f"trade {trade['id']} timestamp"
                        ),
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
                     realized_pnl, commissions, protected_cash, profit_reserve_rate)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    initial_balance=excluded.initial_balance,
                    commission_rate=excluded.commission_rate,
                    cash=excluded.cash,
                    realized_pnl=excluded.realized_pnl,
                    commissions=excluded.commissions,
                    protected_cash=excluded.protected_cash,
                    profit_reserve_rate=excluded.profit_reserve_rate
                """,
                (
                    portfolio.initial_balance,
                    portfolio.commission_rate,
                    portfolio.cash,
                    portfolio.realized_pnl,
                    portfolio.commissions,
                    portfolio.protected_cash,
                    portfolio.profit_reserve_rate,
                ),
            )

            db.execute("DELETE FROM positions")
            db.executemany(
                """
                INSERT INTO positions (
                    ticker, quantity, average_price, purchase_timestamp,
                    purchase_session, purchase_exchange, quote_unavailable_cycles,
                    stagnant_sessions, last_health_status, last_health_candle_timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (p.ticker, p.quantity, p.average_price,
                     p.purchase_timestamp.isoformat() if p.purchase_timestamp else None,
                     p.purchase_session, p.purchase_exchange,
                     p.quote_unavailable_cycles, p.stagnant_sessions,
                     p.last_health_status, p.last_health_candle_timestamp)
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
                    # The account's initial capital is a real equity observation.
                    # Keep it as the drawdown baseline even when the first
                    # market valuation happens only after trades have begun.
                    has_equity_history = db.execute(
                        "SELECT 1 FROM equity_history LIMIT 1"
                    ).fetchone()
                    if not has_equity_history:
                        db.execute(
                            "INSERT INTO equity_history (timestamp, equity) VALUES (?, ?)",
                            (datetime.now().astimezone().isoformat(), portfolio.initial_balance),
                        )
                    db.execute(
                        "INSERT INTO equity_history (timestamp, equity) VALUES (?, ?)",
                        (datetime.now().astimezone().isoformat(), equity),
                    )

            db.commit()
