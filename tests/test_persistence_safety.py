import unittest
from unittest.mock import Mock, patch

from bot.main import CycleConsistencyError, _persist_cycle_safely


class PersistenceSafetyTests(unittest.TestCase):
    def test_portfolio_save_failure_rolls_back_audit_cycle(self):
        audit = Mock()
        audit.record_cycle.return_value = 3
        portfolio_store = Mock()
        save_error = OSError("disk full")
        portfolio_store.save.side_effect = save_error

        with patch("bot.main.time.sleep"):
            with self.assertRaisesRegex(OSError, "disk full"):
                _persist_cycle_safely(
                    portfolio_store,
                    audit,
                    object(),
                    {},
                    cycle_id="cycle-test",
                )

        audit.record_cycle.assert_called_once_with(cycle_id="cycle-test")
        audit.delete_cycle.assert_called_once_with("cycle-test")

    def test_failed_audit_rollback_raises_fatal_consistency_error(self):
        audit = Mock()
        audit.record_cycle.return_value = 1
        audit.delete_cycle.side_effect = OSError("audit database unavailable")
        portfolio_store = Mock()
        portfolio_store.save.side_effect = OSError("portfolio database full")

        with self.assertRaisesRegex(CycleConsistencyError, "manual reconciliation"):
            _persist_cycle_safely(
                portfolio_store,
                audit,
                object(),
                {},
                cycle_id="cycle-test",
            )

        audit.delete_cycle.assert_called_once_with("cycle-test")

    def test_audit_write_failure_does_not_save_portfolio(self):
        audit = Mock()
        audit.record_cycle.side_effect = OSError("audit unavailable")
        portfolio_store = Mock()

        with patch("bot.main.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "after 3 attempts"):
                _persist_cycle_safely(
                    portfolio_store,
                    audit,
                    object(),
                    {},
                    cycle_id="cycle-test",
                )

        self.assertEqual(audit.record_cycle.call_count, 3)
        portfolio_store.save.assert_not_called()
        audit.delete_cycle.assert_not_called()


if __name__ == "__main__":
    unittest.main()
