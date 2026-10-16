import unittest
from unittest.mock import Mock

from bot.main import _record_cycle_with_retries, _validate_held_position_prices


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
