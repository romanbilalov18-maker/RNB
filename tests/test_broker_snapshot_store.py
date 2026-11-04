import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bot.broker_account_snapshot import BrokerAccountSnapshot, BrokerPosition
from bot.broker_snapshot_store import BrokerSnapshotStore, BrokerSnapshotStoreError


class BrokerSnapshotStoreTests(unittest.TestCase):
    def snapshot(self):
        return BrokerAccountSnapshot(
            account_id="account-1",
            currency="RUB",
            available_cash=1000.0,
            blocked_cash=50.0,
            positions=(BrokerPosition("uid-a", "AAA", 2.0, 75.0, "RUB"),),
            open_orders_count=1,
        )

    def test_persists_and_reads_latest_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BrokerSnapshotStore(Path(directory) / "broker.sqlite3")
            stamp = datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc)
            row_id = store.save(self.snapshot(), observed_at=stamp)
            latest = store.latest("account-1")

            self.assertGreater(row_id, 0)
            self.assertEqual(latest, self.snapshot())
            self.assertEqual(latest.total_equity, 1200.0)

    def test_keeps_accounts_separate_and_returns_none_for_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BrokerSnapshotStore(Path(directory) / "broker.sqlite3")
            store.save(self.snapshot())
            self.assertIsNone(store.latest("another-account"))

    def test_rejects_naive_timestamp_and_invalid_values(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BrokerSnapshotStore(Path(directory) / "broker.sqlite3")
            with self.assertRaisesRegex(ValueError, "timezone"):
                store.save(self.snapshot(), observed_at=datetime(2026, 11, 4))
            invalid = BrokerAccountSnapshot("account-1", "RUB", float("nan"), 0, (), 0)
            with self.assertRaisesRegex(ValueError, "available_cash"):
                store.save(invalid)

    def test_detects_corrupt_persisted_position_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broker.sqlite3"
            store = BrokerSnapshotStore(path)
            store.save(self.snapshot())
            with store._connect() as db:
                db.execute("UPDATE broker_snapshots SET positions_json = '{bad'")
            with self.assertRaises(BrokerSnapshotStoreError):
                store.latest("account-1")


    def test_rejects_malformed_but_valid_json_snapshot_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broker.sqlite3"
            store = BrokerSnapshotStore(path)
            store.save(self.snapshot())
            with store._connect() as db:
                db.execute(
                    "UPDATE broker_snapshots SET positions_json = ?",
                    ('[{"instrument_uid":"uid-a","ticker":"AAA","quantity":NaN,"current_price":75,"currency":"RUB"}]',),
                )
            with self.assertRaises(BrokerSnapshotStoreError):
                store.latest("account-1")

    def test_rejects_duplicate_positions_in_stored_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broker.sqlite3"
            store = BrokerSnapshotStore(path)
            store.save(self.snapshot())
            duplicate = (
                '{"instrument_uid":"uid-a","ticker":"AAA","quantity":2,'
                '"current_price":75,"currency":"RUB"},'
                '{"instrument_uid":"uid-a","ticker":"AAA","quantity":1,'
                '"current_price":75,"currency":"RUB"}'
            )
            with store._connect() as db:
                db.execute(
                    "UPDATE broker_snapshots SET positions_json = ?",
                    ("[" + duplicate + "]",),
                )
            with self.assertRaises(BrokerSnapshotStoreError):
                store.latest("account-1")

    def test_latest_if_fresh_accepts_recent_snapshot_and_rejects_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BrokerSnapshotStore(Path(directory) / "broker.sqlite3")
            now = datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc)
            store.save(self.snapshot(), observed_at=now)
            self.assertEqual(
                store.latest_if_fresh("account-1", max_age_seconds=60, now=now),
                self.snapshot(),
            )
            self.assertIsNone(
                store.latest_if_fresh(
                    "account-1",
                    max_age_seconds=60,
                    now=now.replace(minute=2),
                )
            )
            self.assertIsNone(
                store.latest_if_fresh(
                    "account-1",
                    max_age_seconds=60,
                    now=now.replace(minute=1, second=1),
                )
            )

    def test_latest_if_fresh_rejects_invalid_limits_and_clock(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BrokerSnapshotStore(Path(directory) / "broker.sqlite3")
            for invalid in (True, -1, float("nan"), float("inf")):
                with self.subTest(max_age_seconds=invalid):
                    with self.assertRaisesRegex(ValueError, "max_age_seconds"):
                        store.latest_if_fresh(
                            "account-1", max_age_seconds=invalid
                        )
            with self.assertRaisesRegex(ValueError, "timezone"):
                store.latest_if_fresh(
                    "account-1",
                    max_age_seconds=60,
                    now=datetime(2026, 11, 4),
                )

    def test_latest_if_fresh_returns_none_for_future_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BrokerSnapshotStore(Path(directory) / "broker.sqlite3")
            now = datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc)
            store.save(self.snapshot(), observed_at=now.replace(minute=1))
            self.assertIsNone(
                store.latest_if_fresh("account-1", max_age_seconds=60, now=now)
            )

    def test_rejects_position_currency_mismatch_on_save_and_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broker.sqlite3"
            store = BrokerSnapshotStore(path)
            invalid = BrokerAccountSnapshot(
                "account-1", "RUB", 1000.0, 0.0,
                (BrokerPosition("uid-a", "AAA", 2.0, 75.0, "USD"),), 0,
            )
            with self.assertRaisesRegex(ValueError, "currency differs"):
                store.save(invalid)

            store.save(self.snapshot())
            with store._connect() as db:
                db.execute(
                    "UPDATE broker_snapshots SET positions_json = ?",
                    ('[{"instrument_uid":"uid-a","ticker":"AAA","quantity":2,'
                     '"current_price":75,"currency":"USD"}]',),
                )
            with self.assertRaises(BrokerSnapshotStoreError):
                store.latest("account-1")

    def test_rejects_boolean_values_when_loading_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broker.sqlite3"
            store = BrokerSnapshotStore(path)
            store.save(self.snapshot())
            with store._connect() as db:
                db.execute(
                    "UPDATE broker_snapshots SET available_cash = 1",
                )
                db.execute(
                    "UPDATE broker_snapshots SET positions_json = ?",
                    ('[{"instrument_uid":"uid-a","ticker":"AAA","quantity":true,'
                     '"current_price":75,"currency":"RUB"}]',),
                )
            with self.assertRaises(BrokerSnapshotStoreError):
                store.latest("account-1")

    def test_rejects_fractional_open_order_count_in_stored_row(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broker.sqlite3"
            store = BrokerSnapshotStore(path)
            store.save(self.snapshot())
            with store._connect() as db:
                db.execute("UPDATE broker_snapshots SET open_orders_count = 1.5")
            with self.assertRaises(BrokerSnapshotStoreError):
                store.latest("account-1")

if __name__ == "__main__":
    unittest.main()
