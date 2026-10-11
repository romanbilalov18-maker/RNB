from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping


class DecisionAuditStore:
    """Persist recommendations and evaluate forward price outcomes."""

    HORIZONS = (1, 3, 5)

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS decision_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cycle_id TEXT NOT NULL, recorded_at TEXT NOT NULL,
                    ticker TEXT NOT NULL, recommendation TEXT NOT NULL,
                    reason TEXT NOT NULL, score REAL, confidence REAL, consistency REAL,
                    virtual_action TEXT NOT NULL, virtual_quantity INTEGER NOT NULL DEFAULT 0,
                    virtual_commission REAL NOT NULL DEFAULT 0, realized_pnl REAL NOT NULL DEFAULT 0,
                    equity REAL NOT NULL, cash REAL NOT NULL, total_commissions REAL NOT NULL,
                    anchor_price REAL, anchor_session_date TEXT,
                    UNIQUE(cycle_id, ticker))
            """)
            self._ensure_column(db, "decision_audit", "anchor_price", "REAL")
            self._ensure_column(db, "decision_audit", "anchor_session_date", "TEXT")
            db.execute("CREATE INDEX IF NOT EXISTS idx_decision_audit_ticker ON decision_audit(ticker, recorded_at)")
            db.execute("""
                CREATE TABLE IF NOT EXISTS market_session_prices (
                    ticker TEXT NOT NULL, session_date TEXT NOT NULL,
                    close_price REAL NOT NULL CHECK(close_price > 0),
                    PRIMARY KEY(ticker, session_date))
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS decision_outcomes (
                    audit_id INTEGER NOT NULL, horizon_sessions INTEGER NOT NULL,
                    target_session_date TEXT NOT NULL, target_price REAL NOT NULL,
                    raw_return_pct REAL NOT NULL, net_return_pct REAL NOT NULL,
                    direction_correct INTEGER, evaluated_at TEXT NOT NULL,
                    PRIMARY KEY(audit_id, horizon_sessions),
                    FOREIGN KEY(audit_id) REFERENCES decision_audit(id))
            """)
            db.commit()

    @staticmethod
    def _ensure_column(db, table: str, column: str, declaration: str) -> None:
        columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def _connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _session_date(candle: object) -> str | None:
        value = getattr(candle, "time", None) or getattr(candle, "timestamp", None)
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
            except ValueError:
                try:
                    return date.fromisoformat(value[:10]).isoformat()
                except ValueError:
                    return None
        return None

    @staticmethod
    def _price(value: object) -> float | None:
        if value is None:
            return None
        units, nano = getattr(value, "units", None), getattr(value, "nano", None)
        try:
            price = float(units) + float(nano or 0) / 1_000_000_000 if units is not None else float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return price if price > 0 else None

    def record_cycle(
        self, cycle_id: str, decisions: Mapping[str, object], virtual_trades: list,
        *, equity: float, cash: float, total_commissions: float,
        current_prices: Mapping[str, float] | None = None,
        candle_history: Mapping[str, list] | None = None,
        commission_rate: float = 0.0005,
    ) -> int:
        """Record anchor prices, ingest daily closes, and score matured outcomes."""
        current_prices, candle_history = current_prices or {}, candle_history or {}
        actions: dict[str, list] = {}
        for trade in virtual_trades:
            actions.setdefault(trade.ticker, []).append(trade)
        rows, now = [], datetime.now(timezone.utc).isoformat()
        for ticker in sorted(set(decisions) | set(actions)):
            decision, trades = decisions.get(ticker), actions.get(ticker, [])
            candles = candle_history.get(ticker, [])
            # Anchor to the latest completed daily close so price and session date agree.
            anchor_date = self._session_date(candles[-1]) if candles else None
            anchor_price = self._price(getattr(candles[-1], "close", None)) if candles else None
            rows.append((
                cycle_id, now, ticker, getattr(decision, "action", "NO_RECOMMENDATION"),
                getattr(decision, "reason", "нет рекомендации"), getattr(decision, "score", None),
                getattr(decision, "confidence", None), getattr(decision, "consistency", None),
                "+".join(t.side for t in trades) if trades else "NO_TRADE",
                sum(int(t.quantity) for t in trades), sum(float(t.commission) for t in trades),
                sum(float(t.realized_pnl) for t in trades), float(equity), float(cash),
                float(total_commissions), anchor_price, anchor_date,
            ))
        with self._connect() as db:
            db.executemany("""
                INSERT INTO decision_audit (
                    cycle_id, recorded_at, ticker, recommendation, reason, score, confidence,
                    consistency, virtual_action, virtual_quantity, virtual_commission, realized_pnl,
                    equity, cash, total_commissions, anchor_price, anchor_session_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cycle_id, ticker) DO NOTHING
            """, rows)
            for ticker, candles in candle_history.items():
                for candle in candles:
                    session = self._session_date(candle)
                    close = self._price(getattr(candle, "close", None))
                    if session and close:
                        db.execute("""
                            INSERT INTO market_session_prices (ticker, session_date, close_price)
                            VALUES (?, ?, ?) ON CONFLICT(ticker, session_date)
                            DO UPDATE SET close_price=excluded.close_price
                        """, (ticker, session, close))
            self._evaluate_due_outcomes(db, commission_rate)
            db.commit()
        return len(rows)

    def _evaluate_due_outcomes(self, db, commission_rate: float) -> None:
        anchors = db.execute("""
            SELECT id, ticker, recommendation, anchor_price, anchor_session_date
            FROM decision_audit WHERE anchor_price IS NOT NULL AND anchor_session_date IS NOT NULL
        """).fetchall()
        now = datetime.now(timezone.utc).isoformat()
        cost_pct = max(0.0, float(commission_rate)) * 2 * 100
        for anchor in anchors:
            sessions = db.execute("""
                SELECT session_date, close_price FROM market_session_prices
                WHERE ticker=? AND session_date>? ORDER BY session_date ASC
            """, (anchor["ticker"], anchor["anchor_session_date"])).fetchall()
            for horizon in self.HORIZONS:
                if len(sessions) < horizon:
                    continue
                if db.execute("SELECT 1 FROM decision_outcomes WHERE audit_id=? AND horizon_sessions=?",
                              (anchor["id"], horizon)).fetchone():
                    continue
                target = sessions[horizon - 1]
                raw = (float(target["close_price"]) / float(anchor["anchor_price"]) - 1) * 100
                net = raw - cost_pct
                action = anchor["recommendation"]
                correct = int(net > 0) if action == "BUY" else (
                    int(raw < -cost_pct) if action == "SELL" else None)
                db.execute("""
                    INSERT INTO decision_outcomes
                    (audit_id, horizon_sessions, target_session_date, target_price,
                     raw_return_pct, net_return_pct, direction_correct, evaluated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (anchor["id"], horizon, target["session_date"], float(target["close_price"]),
                      raw, net, correct, now))

    def pending_tickers(self) -> set[str]:
        """Tickers whose recorded decisions still lack one or more forward horizons."""
        with self._connect() as db:
            rows = db.execute("""
                SELECT DISTINCT a.ticker
                FROM decision_audit AS a
                WHERE a.anchor_price IS NOT NULL
                  AND a.anchor_session_date IS NOT NULL
                  AND EXISTS (
                      SELECT 1 FROM (
                          SELECT 1 AS horizon UNION ALL SELECT 3 UNION ALL SELECT 5
                      ) AS required
                      WHERE NOT EXISTS (
                          SELECT 1 FROM decision_outcomes AS o
                          WHERE o.audit_id = a.id
                            AND o.horizon_sessions = required.horizon
                      )
                  )
            """).fetchall()
        return {str(row["ticker"]) for row in rows}

    def summary(self) -> dict:
        with self._connect() as db:
            row = db.execute("""
                SELECT COUNT(*) AS observations, COUNT(DISTINCT cycle_id) AS cycles,
                SUM(CASE WHEN recommendation = virtual_action THEN 1 ELSE 0 END) AS exact_action_matches,
                SUM(CASE WHEN virtual_action != 'NO_TRADE' THEN 1 ELSE 0 END) AS observations_with_trades,
                COALESCE(SUM(virtual_commission), 0) AS recorded_trade_commissions,
                COALESCE(SUM(realized_pnl), 0) AS recorded_realized_pnl
                FROM decision_audit
            """).fetchone()
            outcomes = db.execute("""
                SELECT horizon_sessions, COUNT(*) AS evaluated,
                SUM(CASE WHEN direction_correct IS NOT NULL THEN 1 ELSE 0 END) AS scored,
                AVG(CASE WHEN direction_correct IS NOT NULL THEN direction_correct END) AS directional_accuracy,
                AVG(net_return_pct) AS avg_net_return_pct
                FROM decision_outcomes GROUP BY horizon_sessions ORDER BY horizon_sessions
            """).fetchall()
        result = dict(row)
        result["forward_outcomes"] = [dict(item) for item in outcomes]
        return result
