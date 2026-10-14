from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

from bot.intelligence.levels.level_11.models.learning_observation import LearningObservation


class DecisionAuditStore:
    """Persist recommendations and evaluate forward price outcomes."""

    HORIZONS = (1, 3, 5)
    LEARNING_HORIZON = 3
    MAX_LEARNING_OBSERVATIONS_PER_TICKER = 200

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
                    execution_reason TEXT NOT NULL DEFAULT '',
                    entry_price REAL, execution_price REAL,
                    UNIQUE(cycle_id, ticker))
            """)
            self._ensure_column(db, "decision_audit", "anchor_price", "REAL")
            self._ensure_column(db, "decision_audit", "anchor_session_date", "TEXT")
            self._ensure_column(db, "decision_audit", "execution_reason", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(db, "decision_audit", "entry_price", "REAL")
            self._ensure_column(db, "decision_audit", "execution_price", "REAL")
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
            db.execute("""
                CREATE TABLE IF NOT EXISTS decision_learning_snapshots (
                    audit_id INTEGER PRIMARY KEY,
                    level_scores_json TEXT NOT NULL,
                    analyzer_scores_json TEXT NOT NULL,
                    regime TEXT,
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
    def _is_completed_daily_candle(candle: object, now: datetime | None = None) -> bool:
        """Return whether a daily candle is safely beyond its full 24-hour interval."""
        now = now or datetime.now(timezone.utc)
        value = getattr(candle, "time", None) or getattr(candle, "timestamp", None)
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                try:
                    value = date.fromisoformat(value[:10])
                except ValueError:
                    return False
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc) + timedelta(days=1) <= now
        if isinstance(value, date):
            return value < now.date()
        return False

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

    @staticmethod
    def _learning_snapshot(intelligence: object) -> tuple[str, str, str | None]:
        level_scores: dict[str, float] = {}
        analyzer_scores: dict[str, float] = {}
        for number in range(1, 16):
            level_name = f"L{number:02d}"
            level = getattr(intelligence, f"level_{number:02d}", None)
            if level is None:
                continue
            score = getattr(level, "score", None)
            try:
                score = float(score)
            except (TypeError, ValueError, OverflowError):
                score = None
            if score is not None and 0.0 <= score <= 1.0:
                level_scores[level_name] = score

            results = getattr(level, "analyzer_results", ())
            values = results.values() if isinstance(results, Mapping) else results
            for analyzer_result in values or ():
                name = getattr(analyzer_result, "analyzer", None)
                value = getattr(analyzer_result, "score", None)
                if not name:
                    continue
                try:
                    value = float(value)
                except (TypeError, ValueError, OverflowError):
                    continue
                if 0.0 <= value <= 1.0:
                    analyzer_scores[f"{level_name}:{name}"] = value

        level_03 = getattr(intelligence, "level_03", None)
        metadata = getattr(level_03, "metadata", {}) or {}
        regime = metadata.get("regime") or metadata.get("market_regime")
        if regime is not None:
            regime = str(regime)
        return (
            json.dumps(level_scores, sort_keys=True),
            json.dumps(analyzer_scores, sort_keys=True),
            regime,
        )

    def record_cycle(
        self, cycle_id: str, decisions: Mapping[str, object], virtual_trades: list,
        *, equity: float, cash: float, total_commissions: float,
        current_prices: Mapping[str, float] | None = None,
        candle_history: Mapping[str, list] | None = None,
        intelligence_results: Mapping[str, object] | None = None,
        commission_rate: float = 0.0005,
        as_of: datetime | None = None,
    ) -> int:
        """Record recommendations, their L1-L15 snapshot, and matured forward outcomes.

        The outcome anchor is the decision-time market price and calendar date.
        Same-day closing prices are excluded, preventing after-close cycles from
        being scored against a close that was already known when the decision ran.
        """
        current_prices, candle_history = current_prices or {}, candle_history or {}
        intelligence_results = intelligence_results or {}
        as_of = as_of or datetime.now(timezone.utc)
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        as_of = as_of.astimezone(timezone.utc)
        actions: dict[str, list] = {}
        for trade in virtual_trades:
            actions.setdefault(trade.ticker, []).append(trade)
        rows, now = [], as_of.isoformat()
        for ticker in sorted(set(decisions) | set(actions)):
            decision, trades = decisions.get(ticker), actions.get(ticker, [])
            candles = [
                candle for candle in candle_history.get(ticker, [])
                if self._is_completed_daily_candle(candle, now=as_of)
            ]
            # Use the price actually available when the decision was recorded.
            # Outcomes must come from sessions strictly after this calendar date.
            # A stale/missing live price must not create a trainable anchor.
            anchor_price = self._price(current_prices.get(ticker))
            anchor_date = as_of.date().isoformat() if anchor_price is not None else None
            rows.append((
                cycle_id, now, ticker, getattr(decision, "action", "NO_RECOMMENDATION"),
                getattr(decision, "reason", "нет рекомендации"), getattr(decision, "score", None),
                getattr(decision, "confidence", None), getattr(decision, "consistency", None),
                "+".join(t.side for t in trades) if trades else "NO_TRADE",
                sum(int(t.quantity) for t in trades), sum(float(t.commission) for t in trades),
                sum(float(t.realized_pnl) for t in trades), float(equity), float(cash),
                float(total_commissions), anchor_price, anchor_date,
                " | ".join(str(getattr(t, "reason", "not recorded")) for t in trades),
                next((float(t.entry_price) for t in trades if getattr(t, "entry_price", None) is not None), None),
                getattr(trades[-1], "price", None) if trades else None,
            ))
        with self._connect() as db:
            db.executemany("""
                INSERT INTO decision_audit (
                    cycle_id, recorded_at, ticker, recommendation, reason, score, confidence,
                    consistency, virtual_action, virtual_quantity, virtual_commission, realized_pnl,
                    equity, cash, total_commissions, anchor_price, anchor_session_date,
                    execution_reason, entry_price, execution_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cycle_id, ticker) DO UPDATE SET
                    anchor_price=COALESCE(decision_audit.anchor_price, excluded.anchor_price),
                    anchor_session_date=COALESCE(decision_audit.anchor_session_date, excluded.anchor_session_date)
            """, rows)

            for ticker, intelligence in intelligence_results.items():
                audit = db.execute(
                    "SELECT id FROM decision_audit WHERE cycle_id=? AND ticker=?",
                    (cycle_id, ticker),
                ).fetchone()
                if audit is None:
                    continue
                level_json, analyzer_json, regime = self._learning_snapshot(intelligence)
                db.execute("""
                    INSERT INTO decision_learning_snapshots
                    (audit_id, level_scores_json, analyzer_scores_json, regime)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(audit_id) DO NOTHING
                """, (audit["id"], level_json, analyzer_json, regime))

            for ticker, raw_candles in candle_history.items():
                for candle in raw_candles:
                    if not self._is_completed_daily_candle(candle, now=as_of):
                        continue
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

    def learning_observations_by_ticker(self) -> dict[str, tuple[LearningObservation, ...]]:
        """Return only matured, scored 3-session outcomes with their original L1-L15 scores."""
        grouped: dict[str, list[LearningObservation]] = {}
        with self._connect() as db:
            rows = db.execute("""
                SELECT a.ticker, o.net_return_pct, o.direction_correct,
                       s.level_scores_json, s.analyzer_scores_json, s.regime
                FROM decision_outcomes AS o
                JOIN decision_audit AS a ON a.id = o.audit_id
                JOIN decision_learning_snapshots AS s ON s.audit_id = a.id
                WHERE o.horizon_sessions=? AND o.direction_correct IS NOT NULL
                ORDER BY o.evaluated_at ASC, o.audit_id ASC
            """, (self.LEARNING_HORIZON,)).fetchall()
        for row in rows:
            try:
                level_scores = json.loads(row["level_scores_json"])
                analyzer_scores = json.loads(row["analyzer_scores_json"])
                observation = LearningObservation(
                    outcome_return=float(row["net_return_pct"]) / 100.0,
                    correct=bool(row["direction_correct"]),
                    level_scores=level_scores,
                    analyzer_scores=analyzer_scores,
                    regime=row["regime"],
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                # Ignore malformed legacy/corrupt records rather than breaking a live cycle.
                continue
            grouped.setdefault(str(row["ticker"]), []).append(observation)
        return {
            ticker: tuple(observations[-self.MAX_LEARNING_OBSERVATIONS_PER_TICKER:])
            for ticker, observations in grouped.items()
        }

    def pending_tickers(self) -> set[str]:
        """Tickers whose recorded decisions still lack one or more forward horizons."""
        with self._connect() as db:
            rows = db.execute("""
                SELECT DISTINCT a.ticker
                FROM decision_audit AS a
                WHERE (
                  a.anchor_price IS NULL OR a.anchor_session_date IS NULL
                  OR EXISTS (
                      SELECT 1 FROM (
                          SELECT 1 AS horizon UNION ALL SELECT 3 UNION ALL SELECT 5
                      ) AS required
                      WHERE NOT EXISTS (
                          SELECT 1 FROM decision_outcomes AS o
                          WHERE o.audit_id = a.id
                            AND o.horizon_sessions = required.horizon
                      )
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
        result["learning_observations"] = sum(
            item["scored"] for item in result["forward_outcomes"]
            if item["horizon_sessions"] == self.LEARNING_HORIZON
        )
        return result
