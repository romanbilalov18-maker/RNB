import unittest
from unittest.mock import Mock

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
