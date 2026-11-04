import unittest

from bot.broker_account_snapshot import BrokerAccountSnapshot, BrokerPosition
from bot.broker_reconciliation import BrokerLedgerSnapshot, reconcile_broker_snapshot


def actual_snapshot(*, cash=1000.0, blocked=100.0, qty=3.0, open_orders=0, account="acct", currency="RUB"):
    return BrokerAccountSnapshot(
        account_id=account,
        currency=currency,
        available_cash=cash,
        blocked_cash=blocked,
        positions=(BrokerPosition("uid-a", "AAA", qty, 50.0, currency),),
        open_orders_count=open_orders,
    )


def expected_ledger(*, cash=1000.0, blocked=100.0, qty=3.0, account="acct", currency="RUB"):
    return BrokerLedgerSnapshot(
        account_id=account,
        currency=currency,
        available_cash=cash,
        blocked_cash=blocked,
        positions_by_uid={"uid-a": qty},
    )


class BrokerReconciliationTests(unittest.TestCase):
    def test_matching_snapshots_pass(self):
        report = reconcile_broker_snapshot(actual_snapshot(), expected_ledger())
        self.assertTrue(report.matched)
        self.assertEqual(report.differences, ())
        self.assertEqual(report.blockers, ())

    def test_cash_difference_is_reported_and_blocks(self):
        report = reconcile_broker_snapshot(actual_snapshot(cash=980), expected_ledger())
        self.assertFalse(report.matched)
        self.assertEqual(report.differences[0].field, "available_cash")
        self.assertIn("broker ledger does not match current broker snapshot", report.blockers)

    def test_missing_or_extra_positions_are_reported(self):
        report = reconcile_broker_snapshot(
            actual_snapshot(qty=4), expected_ledger(qty=3)
        )
        self.assertFalse(report.matched)
        self.assertEqual(report.differences[0].field, "position:uid-a")

        expected_empty = BrokerLedgerSnapshot("acct", "RUB", 1000, 100, {})
        report = reconcile_broker_snapshot(actual_snapshot(), expected_empty)
        self.assertEqual(report.differences[0].field, "position:uid-a")

    def test_account_or_currency_mismatch_blocks(self):
        report = reconcile_broker_snapshot(
            actual_snapshot(account="other"), expected_ledger()
        )
        self.assertFalse(report.matched)
        self.assertIn("account identity mismatch", report.blockers)

        report = reconcile_broker_snapshot(
            actual_snapshot(currency="USD"), expected_ledger()
        )
        self.assertFalse(report.matched)
        self.assertIn("account currency mismatch", report.blockers)

    def test_open_orders_block_even_when_balances_match(self):
        report = reconcile_broker_snapshot(
            actual_snapshot(open_orders=2), expected_ledger()
        )
        self.assertFalse(report.matched)
        self.assertIn("2 open/unresolved broker order(s)", report.blockers)

    def test_tolerances_and_expected_values_are_validated(self):
        with self.assertRaises(ValueError):
            reconcile_broker_snapshot(actual_snapshot(), expected_ledger(), cash_tolerance=float("nan"))
        with self.assertRaises(ValueError):
            reconcile_broker_snapshot(actual_snapshot(), expected_ledger(qty=-1))

    def test_invalid_actual_snapshot_values_fail_closed(self):
        for invalid_cash in (float("nan"), float("inf"), -1, True):
            with self.subTest(cash=invalid_cash):
                with self.assertRaises(ValueError):
                    reconcile_broker_snapshot(
                        actual_snapshot(cash=invalid_cash), expected_ledger()
                    )

        with self.assertRaisesRegex(ValueError, "open_orders_count"):
            reconcile_broker_snapshot(
                actual_snapshot(open_orders=-1), expected_ledger()
            )

    def test_duplicate_actual_position_uids_fail_closed(self):
        snapshot = BrokerAccountSnapshot(
            account_id="acct",
            currency="RUB",
            available_cash=1000,
            blocked_cash=100,
            positions=(
                BrokerPosition("uid-a", "AAA", 3, 50, "RUB"),
                BrokerPosition("uid-a", "AAA", 3, 50, "RUB"),
            ),
            open_orders_count=0,
        )
        with self.assertRaisesRegex(ValueError, "duplicate actual position"):
            reconcile_broker_snapshot(snapshot, expected_ledger())

    def test_invalid_actual_or_expected_quantities_fail_closed(self):
        invalid_actual = actual_snapshot(qty=float("nan"))
        with self.assertRaisesRegex(ValueError, "actual quantity"):
            reconcile_broker_snapshot(invalid_actual, expected_ledger())

        invalid_expected = BrokerLedgerSnapshot(
            "acct", "RUB", 1000, 100, {"uid-a": float("inf")}
        )
        with self.assertRaisesRegex(ValueError, "expected quantity"):
            reconcile_broker_snapshot(actual_snapshot(), invalid_expected)


if __name__ == "__main__":
    unittest.main()
