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


if __name__ == "__main__":
    unittest.main()
