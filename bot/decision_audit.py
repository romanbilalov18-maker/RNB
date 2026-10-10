from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


class DecisionAuditStore:
    """Persist recommendation-vs-paper-execution observations separately from the portfolio."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS decision_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cycle_id TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    score REAL,
                    confidence REAL,
                    consistency REAL,
                    virtual_action TEXT NOT NULL,
                    virtual_quantity INTEGER NOT NULL DEFAULT 0,
                    virtual_commission REAL NOT NULL DEFAULT 0,
                    realized_pnl REAL NOT NULL DEFAULT 0,
                    equity REAL NOT NULL,
                    cash REAL NOT NULL,
                    total_commissions REAL NOT NULL,
                    UNIQUE(cycle_id, ticker)
                )
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_decision_audit_ticker
                ON decision_audit(ticker, recorded_at)
                """
            )

    def _connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def record_cycle(
        self,
        cycle_id: str,
        decisions: Mapping[str, object],
        virtual_trades: list,
        *,
        equity: float,
        cash: float,
        total_commissions: float,
    ) -> int:
        """Record each recommendation and resulting virtual action; never executes trades."""
        actions: dict[str, list] = {}
        for trade in virtual_trades:
            actions.setdefault(trade.ticker, []).append(trade)

        tickers = set(decisions) | set(actions)
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for ticker in sorted(tickers):
            decision = decisions.get(ticker)
            trades = actions.get(ticker, [])
            action = "+".join(trade.side for trade in trades) if trades else "NO_TRADE"
            rows.append(
                (
                    cycle_id,
                    now,
                    ticker,
                    getattr(decision, "action", "NO_RECOMMENDATION"),
                    getattr(decision, "reason", "нет рекомендации"),
                    getattr(decision, "score", None),
                    getattr(decision, "confidence", None),
                    getattr(decision, "consistency", None),
                    action,
                    sum(int(trade.quantity) for trade in trades),
                    sum(float(trade.commission) for trade in trades),
                    sum(float(trade.realized_pnl) for trade in trades),
                    float(equity),
                    float(cash),
                    float(total_commissions),
                )
            )

        with self._connect() as db:
            db.executemany(
                """
                INSERT INTO decision_audit (
                    cycle_id, recorded_at, ticker, recommendation, reason,
                    score, confidence, consistency, virtual_action,
                    virtual_quantity, virtual_commission, realized_pnl,
                    equity, cash, total_commissions
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cycle_id, ticker) DO NOTHING
                """,
                rows,
            )
            db.commit()
        return len(rows)

    def summary(self) -> dict:
        """Return auditable counts and outcome totals from the audit journal."""
        with self._connect() as db:
            row = db.execute(
                """
                SELECT
                    COUNT(*) AS observations,
                    COUNT(DISTINCT cycle_id) AS cycles,
                    SUM(CASE WHEN recommendation = virtual_action THEN 1 ELSE 0 END)
                        AS exact_action_matches,
                    SUM(CASE WHEN virtual_action != 'NO_TRADE' THEN 1 ELSE 0 END)
                        AS observations_with_trades,
                    COALESCE(SUM(virtual_commission), 0) AS recorded_trade_commissions,
                    COALESCE(SUM(realized_pnl), 0) AS recorded_realized_pnl
                FROM decision_audit
                """
            ).fetchone()
        return dict(row)
