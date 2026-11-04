"""Durable history for read-only broker snapshots.

This database is kept separate from the virtual portfolio. It stores observed
broker values only; it never invents a starting balance or submits broker orders.
"""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bot.broker_account_snapshot import BrokerAccountSnapshot, BrokerPosition


class BrokerSnapshotStoreError(RuntimeError):
    """Stored broker snapshot data is missing or corrupted."""


class BrokerSnapshotStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS broker_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    available_cash REAL NOT NULL CHECK (available_cash >= 0),
                    blocked_cash REAL NOT NULL CHECK (blocked_cash >= 0),
                    open_orders_count INTEGER NOT NULL CHECK (open_orders_count >= 0),
                    positions_json TEXT NOT NULL
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_broker_snapshots_account_time
                ON broker_snapshots(account_id, observed_at, id)
            """)

    def save(
        self,
        snapshot: BrokerAccountSnapshot,
        *,
        observed_at: datetime | None = None,
    ) -> int:
        timestamp = observed_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        if not snapshot.account_id.strip() or not snapshot.currency.strip():
            raise ValueError("account_id and currency are required")
        if (
            isinstance(snapshot.open_orders_count, bool)
            or not isinstance(snapshot.open_orders_count, int)
            or snapshot.open_orders_count < 0
        ):
            raise ValueError("open_orders_count must be a non-negative integer")
        for field in ("available_cash", "blocked_cash"):
            value = getattr(snapshot, field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{field} must be finite and non-negative")

        position_rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for position in snapshot.positions:
            if not position.instrument_uid.strip() or position.instrument_uid in seen:
                raise ValueError("positions must have unique non-empty instrument_uid values")
            seen.add(position.instrument_uid)
            if (
                isinstance(position.quantity, bool)
                or not isinstance(position.quantity, (int, float))
                or not math.isfinite(position.quantity)
                or position.quantity <= 0
                or isinstance(position.current_price, bool)
                or not isinstance(position.current_price, (int, float))
                or not math.isfinite(position.current_price)
                or position.current_price <= 0
            ):
                raise ValueError(f"position {position.instrument_uid} has invalid quantity or price")
            position_rows.append({
                "instrument_uid": position.instrument_uid,
                "ticker": position.ticker,
                "quantity": float(position.quantity),
                "current_price": float(position.current_price),
                "currency": position.currency,
            })

        with self._connect() as db:
            cursor = db.execute(
                """INSERT INTO broker_snapshots
                   (account_id, observed_at, currency, available_cash, blocked_cash,
                    open_orders_count, positions_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot.account_id,
                    timestamp.astimezone(timezone.utc).isoformat(),
                    snapshot.currency.upper(),
                    float(snapshot.available_cash),
                    float(snapshot.blocked_cash),
                    snapshot.open_orders_count,
                    json.dumps(position_rows, separators=(",", ":"), sort_keys=True),
                ),
            )
            return int(cursor.lastrowid)

    def latest_observed_at(self, account_id: str) -> datetime | None:
        """Return the UTC timestamp for the latest stored snapshot, if present."""
        account_id = account_id.strip()
        if not account_id:
            raise ValueError("account_id is required")
        with self._connect() as db:
            row = db.execute(
                """SELECT observed_at FROM broker_snapshots WHERE account_id = ?
                   ORDER BY observed_at DESC, id DESC LIMIT 1""",
                (account_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            timestamp = datetime.fromisoformat(str(row["observed_at"]))
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("stored timestamp has no timezone")
            return timestamp.astimezone(timezone.utc)
        except (TypeError, ValueError) as exc:
            raise BrokerSnapshotStoreError(
                "latest stored broker snapshot has an invalid timestamp"
            ) from exc

    def latest_if_fresh(
        self,
        account_id: str,
        *,
        max_age_seconds: float,
        now: datetime | None = None,
    ) -> BrokerAccountSnapshot | None:
        """Return latest snapshot only if its timestamp is within the freshness limit.

        Missing snapshots return None. Invalid limits/timestamps fail closed.
        """
        if (
            isinstance(max_age_seconds, bool)
            or not isinstance(max_age_seconds, (int, float))
            or not math.isfinite(max_age_seconds)
            or max_age_seconds < 0
        ):
            raise ValueError("max_age_seconds must be finite and non-negative")
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("now must include a timezone")
        observed_at = self.latest_observed_at(account_id)
        if observed_at is None:
            return None
        age = (current.astimezone(timezone.utc) - observed_at).total_seconds()
        if age < 0 or age > max_age_seconds:
            return None
        return self.latest(account_id)

    def latest(self, account_id: str) -> BrokerAccountSnapshot | None:
        account_id = account_id.strip()
        if not account_id:
            raise ValueError("account_id is required")
        with self._connect() as db:
            row = db.execute(
                """SELECT * FROM broker_snapshots WHERE account_id = ?
                   ORDER BY observed_at DESC, id DESC LIMIT 1""",
                (account_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            raw_positions = json.loads(row["positions_json"])
            if not isinstance(raw_positions, list):
                raise ValueError("positions_json must contain a list")
            positions_list: list[BrokerPosition] = []
            seen_uids: set[str] = set()
            for item in raw_positions:
                if not isinstance(item, dict):
                    raise ValueError("position row must be an object")
                uid = str(item["instrument_uid"]).strip()
                ticker = str(item["ticker"]).strip()
                currency = str(item["currency"]).strip().upper()
                quantity = float(item["quantity"])
                current_price = float(item["current_price"])
                if not uid or uid in seen_uids or not ticker or not currency:
                    raise ValueError("position identity is missing or duplicated")
                if (
                    not math.isfinite(quantity)
                    or quantity <= 0
                    or not math.isfinite(current_price)
                    or current_price <= 0
                ):
                    raise ValueError("position quantity and price must be finite and positive")
                seen_uids.add(uid)
                positions_list.append(
                    BrokerPosition(uid, ticker, quantity, current_price, currency)
                )

            account_id_value = str(row["account_id"]).strip()
            currency_value = str(row["currency"]).strip().upper()
            available_cash = float(row["available_cash"])
            blocked_cash = float(row["blocked_cash"])
            open_orders_count = int(row["open_orders_count"])
            if not account_id_value or not currency_value:
                raise ValueError("account identity is missing")
            if (
                not math.isfinite(available_cash)
                or available_cash < 0
                or not math.isfinite(blocked_cash)
                or blocked_cash < 0
                or open_orders_count < 0
            ):
                raise ValueError("stored account values are invalid")
            positions = tuple(positions_list)
            return BrokerAccountSnapshot(
                account_id=account_id_value,
                currency=currency_value,
                available_cash=available_cash,
                blocked_cash=blocked_cash,
                positions=positions,
                open_orders_count=open_orders_count,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise BrokerSnapshotStoreError(
                f"stored broker snapshot #{row['id']} is corrupted"
            ) from exc
