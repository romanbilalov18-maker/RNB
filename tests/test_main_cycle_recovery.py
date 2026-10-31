import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from bot.decision_audit import DecisionAuditStore
from bot.portfolio_store import SQLitePortfolioStore
from bot.virtual_portfolio import VirtualPortfolio
from bot.main import (
    CycleConsistencyError,
    _persist_cycle_safely,
    _reconcile_cycle_history,
    _record_cycle_with_retries,
    _validate_held_position_prices,
)





class _PortfolioStoreDouble:
    def __init__(self, committed=(), save_error=None):
        self.committed = set(committed)
        self.save_error = save_error
        self.save_calls = 0

    def committed_cycle_ids(self):
        return set(self.committed)

    def save(self, *args, **kwargs):
        self.save_calls += 1
        if self.save_error:
            raise self.save_error


class _AuditStoreDouble:
    def __init__(self, cycles=(), record_count=1, rollback_error=None):
        self.cycles = set(cycles)
        self.record_count = record_count
        self.rollback_error = rollback_error
        self.record_calls = 0
        self.deleted = []

    def cycle_ids(self):
        return set(self.cycles)

    def cycle_record_count(self, cycle_id):
        return self.record_count

    def record_cycle(self, *, cycle_id, **kwargs):
        self.record_calls += 1
        self.cycles.add(cycle_id)
        return self.record_count

    def delete_cycle(self, cycle_id):
        if self.rollback_error:
            raise self.rollback_error
        self.deleted.append(cycle_id)
        self.cycles.discard(cycle_id)


class TestMainCycleRecoveryGuards(unittest.TestCase):
    def test_missing_price_for_held_position_rejects_cycle(self):
        portfolio = Mock()
        portfolio.positions = {"AAA": Mock(), "BBB": Mock()}

        with self.assertRaisesRegex(RuntimeError, "BBB"):
            _validate_held_position_prices(portfolio, {"AAA": 100.0})

    def test_complete_prices_allow_cycle(self):
        portfolio = Mock()
        portfolio.positions = {"AAA": Mock(), "BBB": Mock()}

        _validate_held_position_prices(portfolio, {"AAA": 100.0, "BBB": 50.0})

    def test_startup_removes_orphan_audit_cycle_after_interrupted_portfolio_commit(self):
        portfolio_store = Mock()
        audit_store = Mock()
        portfolio_store.cycle_tracking_initialized.return_value = True
        portfolio_store.committed_cycle_ids.return_value = {"cycle-committed"}
        audit_store.cycle_ids.return_value = {"cycle-committed", "cycle-audit-only"}

        _reconcile_cycle_history(portfolio_store, audit_store)

        audit_store.delete_cycle.assert_called_once_with("cycle-audit-only")

    def test_startup_fails_closed_when_committed_cycle_has_no_audit(self):
        portfolio_store = Mock()
        audit_store = Mock()
        portfolio_store.cycle_tracking_initialized.return_value = True
        portfolio_store.committed_cycle_ids.return_value = {"cycle-portfolio-only"}
        audit_store.cycle_ids.return_value = set()

        with self.assertRaisesRegex(CycleConsistencyError, "missing from decision audit"):
            _reconcile_cycle_history(portfolio_store, audit_store)

        audit_store.delete_cycle.assert_not_called()

    def test_persist_rejects_cycle_already_present_only_in_audit(self):
        portfolio_store = _PortfolioStoreDouble()
        audit_store = _AuditStoreDouble(cycles={"cycle-orphan"})

        with self.assertRaisesRegex(CycleConsistencyError, "already exists in audit"):
            _persist_cycle_safely(
                portfolio_store, audit_store, Mock(), {},
                cycle_id="cycle-orphan", decisions={}, virtual_trades=[],
                equity=1000.0, cash=1000.0, total_commissions=0.0,
            )

        self.assertEqual(audit_store.record_calls, 0)
        self.assertEqual(portfolio_store.save_calls, 0)

    def test_persist_returns_existing_committed_cycle_without_replaying(self):
        portfolio_store = _PortfolioStoreDouble(committed={"cycle-done"})
        audit_store = _AuditStoreDouble(cycles={"cycle-done"}, record_count=2)

        result = _persist_cycle_safely(
            portfolio_store, audit_store, Mock(), {},
            cycle_id="cycle-done", decisions={}, virtual_trades=[],
            equity=1000.0, cash=1000.0, total_commissions=0.0,
        )

        self.assertEqual(result, 2)
        self.assertEqual(audit_store.record_calls, 0)
        self.assertEqual(portfolio_store.save_calls, 0)

    def test_failed_portfolio_save_rolls_back_audit_cycle(self):
        portfolio_store = _PortfolioStoreDouble(save_error=OSError("disk full"))
        audit_store = _AuditStoreDouble(record_count=1)

        with self.assertRaisesRegex(OSError, "disk full"):
            _persist_cycle_safely(
                portfolio_store, audit_store, Mock(), {},
                cycle_id="cycle-rollback", decisions={}, virtual_trades=[],
                equity=1000.0, cash=1000.0, total_commissions=0.0,
            )

        self.assertEqual(audit_store.deleted, ["cycle-rollback"])

    def test_failed_audit_rollback_raises_consistency_error(self):
        portfolio_store = _PortfolioStoreDouble(save_error=OSError("disk full"))
        audit_store = _AuditStoreDouble(
            record_count=1, rollback_error=OSError("audit locked")
        )

        with self.assertRaisesRegex(CycleConsistencyError, "manual reconciliation"):
            _persist_cycle_safely(
                portfolio_store, audit_store, Mock(), {},
                cycle_id="cycle-ambiguous", decisions={}, virtual_trades=[],
                equity=1000.0, cash=1000.0, total_commissions=0.0,
            )

    def _create_sqlite_stores(self, directory):
        root = Path(directory)
        portfolio_store = SQLitePortfolioStore(root / "portfolio.sqlite3")
        audit_store = DecisionAuditStore(root / "decision_audit.sqlite3")
        portfolio_store.mark_cycle_tracking_initialized()
        return portfolio_store, audit_store

    def _record_sqlite_audit_cycle(self, audit_store, cycle_id):
        return audit_store.record_cycle(
            cycle_id=cycle_id,
            decisions={
                "AAA": SimpleNamespace(action="HOLD", reason="integration recovery test")
            },
            virtual_trades=[],
            equity=10_000.0,
            cash=10_000.0,
            total_commissions=0.0,
            current_prices={"AAA": 100.0},
            as_of=datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc),
        )

    def test_real_sqlite_startup_removes_audit_only_cycle_after_interruption(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_store, audit_store = self._create_sqlite_stores(directory)
            self._record_sqlite_audit_cycle(audit_store, "interrupted-cycle")

            self.assertEqual(audit_store.cycle_ids(), {"interrupted-cycle"})
            self.assertEqual(portfolio_store.committed_cycle_ids(), set())

            _reconcile_cycle_history(portfolio_store, audit_store)

            self.assertEqual(audit_store.cycle_ids(), set())
            self.assertEqual(portfolio_store.committed_cycle_ids(), set())

    def test_real_sqlite_startup_fails_closed_for_portfolio_cycle_without_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_store, audit_store = self._create_sqlite_stores(directory)
            portfolio_store.save(
                VirtualPortfolio(10_000.0), cycle_id="portfolio-only-cycle"
            )

            with self.assertRaisesRegex(
                CycleConsistencyError, "missing from decision audit"
            ):
                _reconcile_cycle_history(portfolio_store, audit_store)

            self.assertEqual(
                portfolio_store.committed_cycle_ids(), {"portfolio-only-cycle"}
            )

    def test_real_sqlite_cycle_persistence_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_store, audit_store = self._create_sqlite_stores(directory)
            portfolio = VirtualPortfolio(10_000.0)
            kwargs = {
                "decisions": {
                    "AAA": SimpleNamespace(action="HOLD", reason="idempotency test")
                },
                "virtual_trades": [],
                "equity": 10_000.0,
                "cash": 10_000.0,
                "total_commissions": 0.0,
                "current_prices": {"AAA": 100.0},
                "as_of": datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc),
            }

            first = _persist_cycle_safely(
                portfolio_store, audit_store, portfolio, {"AAA": 100.0},
                cycle_id="idempotent-cycle", **kwargs,
            )
            second = _persist_cycle_safely(
                portfolio_store, audit_store, portfolio, {"AAA": 100.0},
                cycle_id="idempotent-cycle", **kwargs,
            )

            self.assertEqual(first, 1)
            self.assertEqual(second, 1)
            self.assertEqual(portfolio_store.committed_cycle_ids(), {"idempotent-cycle"})
            self.assertEqual(audit_store.cycle_record_count("idempotent-cycle"), 1)

    def test_real_sqlite_audit_rollback_is_atomic_when_parent_delete_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_store, audit_store = self._create_sqlite_stores(directory)
            self._record_sqlite_audit_cycle(audit_store, "delete-failure-cycle")
            with audit_store._connect() as db:
                audit_id = db.execute(
                    "SELECT id FROM decision_audit WHERE cycle_id=?",
                    ("delete-failure-cycle",),
                ).fetchone()["id"]
                db.execute(
                    "INSERT INTO decision_outcomes "
                    "(audit_id, horizon_sessions, target_session_date, target_price, "
                    "raw_return_pct, net_return_pct, direction_correct, evaluated_at) "
                    "VALUES (?, 1, '2026-11-01', 101.0, 1.0, 0.9, 1, '2026-10-31T12:00:00+00:00')",
                    (audit_id,),
                )
                db.execute(
                    "INSERT INTO decision_learning_snapshots "
                    "(audit_id, level_scores_json, analyzer_scores_json, regime) "
                    "VALUES (?, '{}', '{}', 'test')",
                    (audit_id,),
                )
                db.execute(
                    "CREATE TRIGGER block_audit_parent_delete "
                    "BEFORE DELETE ON decision_audit "
                    "BEGIN SELECT RAISE(ABORT, 'simulated parent delete failure'); END"
                )

            with self.assertRaisesRegex(sqlite3.IntegrityError, "simulated parent delete failure"):
                audit_store.delete_cycle("delete-failure-cycle")

            with audit_store._connect() as db:
                self.assertEqual(
                    db.execute(
                        "SELECT COUNT(*) FROM decision_audit WHERE cycle_id=?",
                        ("delete-failure-cycle",),
                    ).fetchone()[0],
                    1,
                )
                self.assertEqual(
                    db.execute(
                        "SELECT COUNT(*) FROM decision_outcomes WHERE audit_id=?",
                        (audit_id,),
                    ).fetchone()[0],
                    1,
                )
                self.assertEqual(
                    db.execute(
                        "SELECT COUNT(*) FROM decision_learning_snapshots WHERE audit_id=?",
                        (audit_id,),
                    ).fetchone()[0],
                    1,
                )

    def test_real_sqlite_portfolio_save_failure_rolls_back_audit_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_store, audit_store = self._create_sqlite_stores(directory)
            original_save = portfolio_store.save

            def fail_before_portfolio_commit(*args, **kwargs):
                raise OSError("simulated process interruption before portfolio commit")

            portfolio_store.save = fail_before_portfolio_commit
            try:
                with self.assertRaisesRegex(OSError, "simulated process interruption"):
                    _persist_cycle_safely(
                        portfolio_store,
                        audit_store,
                        VirtualPortfolio(10_000.0),
                        {"AAA": 100.0},
                        cycle_id="sqlite-rollback-cycle",
                        decisions={
                            "AAA": SimpleNamespace(action="HOLD", reason="rollback test")
                        },
                        virtual_trades=[],
                        equity=10_000.0,
                        cash=10_000.0,
                        total_commissions=0.0,
                        current_prices={"AAA": 100.0},
                        as_of=datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc),
                    )
            finally:
                portfolio_store.save = original_save

            self.assertEqual(audit_store.cycle_ids(), set())
            self.assertEqual(portfolio_store.committed_cycle_ids(), set())

    def test_audit_write_retries_with_same_cycle_id(self):
        audit_store = Mock()
        audit_store.record_cycle.side_effect = [OSError("temporary lock"), 4]

        result = _record_cycle_with_retries(audit_store, cycle_id="cycle-7", equity=1000.0)

        self.assertEqual(result, 4)
        self.assertEqual(audit_store.record_cycle.call_count, 2)
        self.assertEqual(audit_store.record_cycle.call_args_list[0].kwargs["cycle_id"], "cycle-7")
        self.assertEqual(audit_store.record_cycle.call_args_list[1].kwargs["cycle_id"], "cycle-7")

    def test_audit_write_raises_after_bounded_retries(self):
        audit_store = Mock()
        audit_store.record_cycle.side_effect = OSError("database unavailable")

        with self.assertRaisesRegex(RuntimeError, "failed after 3 attempts"):
            _record_cycle_with_retries(audit_store, cycle_id="cycle-8", equity=1000.0)

        self.assertEqual(audit_store.record_cycle.call_count, 3)


if __name__ == "__main__":
    unittest.main()
