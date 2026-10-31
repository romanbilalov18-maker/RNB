import unittest
from unittest.mock import Mock

from bot.main import (
    CycleConsistencyError,
    _persist_cycle_safely,
    _reconcile_cycle_history,
    _record_cycle_with_retries,
    _validate_held_position_prices,
)


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
        portfolio_store = Mock()
        audit_store = Mock()
        portfolio_store.committed_cycle_ids.return_value = set()
        audit_store.cycle_ids.return_value = {"cycle-orphan"}

        with self.assertRaisesRegex(CycleConsistencyError, "already exists in audit"):
            _persist_cycle_safely(
                portfolio_store, audit_store, Mock(), {},
                cycle_id="cycle-orphan", decisions={}, virtual_trades=[],
                equity=1000.0, cash=1000.0, total_commissions=0.0,
            )

        audit_store.record_cycle.assert_not_called()
        portfolio_store.save.assert_not_called()

    def test_persist_returns_existing_committed_cycle_without_replaying(self):
        portfolio_store = Mock()
        audit_store = Mock()
        portfolio_store.committed_cycle_ids.return_value = {"cycle-done"}
        audit_store.cycle_ids.return_value = {"cycle-done"}
        audit_store.cycle_record_count.return_value = 2

        result = _persist_cycle_safely(
            portfolio_store, audit_store, Mock(), {},
            cycle_id="cycle-done", decisions={}, virtual_trades=[],
            equity=1000.0, cash=1000.0, total_commissions=0.0,
        )

        self.assertEqual(result, 2)
        audit_store.record_cycle.assert_not_called()
        portfolio_store.save.assert_not_called()

    def test_failed_portfolio_save_rolls_back_audit_cycle(self):
        portfolio_store = Mock()
        audit_store = Mock()
        portfolio_store.committed_cycle_ids.return_value = set()
        audit_store.cycle_ids.return_value = set()
        audit_store.record_cycle.return_value = 1
        portfolio_store.save.side_effect = OSError("disk full")

        with self.assertRaisesRegex(OSError, "disk full"):
            _persist_cycle_safely(
                portfolio_store, audit_store, Mock(), {},
                cycle_id="cycle-rollback", decisions={}, virtual_trades=[],
                equity=1000.0, cash=1000.0, total_commissions=0.0,
            )

        audit_store.delete_cycle.assert_called_once_with("cycle-rollback")

    def test_failed_audit_rollback_raises_consistency_error(self):
        portfolio_store = Mock()
        audit_store = Mock()
        portfolio_store.committed_cycle_ids.return_value = set()
        audit_store.cycle_ids.return_value = set()
        audit_store.record_cycle.return_value = 1
        portfolio_store.save.side_effect = OSError("disk full")
        audit_store.delete_cycle.side_effect = OSError("audit locked")

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
