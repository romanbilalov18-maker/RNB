import unittest

from bot.order_lifecycle import OrderLifecycle, OrderStatus


def order():
    return OrderLifecycle("rnb-uuid", requested_quantity=10)


class OrderLifecycleTests(unittest.TestCase):
    def test_partial_then_full_fill(self):
        partial = order().update(
            OrderStatus.SUBMITTED, filled_quantity=0, average_fill_price=None
        ).update(
            OrderStatus.PARTIALLY_FILLED, filled_quantity=4, average_fill_price=101.25
        )
        self.assertTrue(partial.retry_blocked)
        filled = partial.update(
            OrderStatus.FILLED, filled_quantity=10, average_fill_price=101.5
        )
        self.assertEqual(filled.filled_quantity, 10)
        self.assertEqual(filled.average_fill_price, 101.5)

    def test_unknown_blocks_resubmission_until_reconciled(self):
        unknown = order().update(
            OrderStatus.UNKNOWN, filled_quantity=0, average_fill_price=None
        )
        self.assertTrue(unknown.retry_blocked)
        self.assertTrue(
            unknown.update(
                OrderStatus.SUBMITTED, filled_quantity=0, average_fill_price=None
            ).retry_blocked
        )

    def test_fill_requires_quantity_and_price(self):
        submitted = order().update(
            OrderStatus.SUBMITTED, filled_quantity=0, average_fill_price=None
        )
        with self.assertRaises(ValueError):
            submitted.update(
                OrderStatus.FILLED, filled_quantity=5, average_fill_price=100
            )
        with self.assertRaises(ValueError):
            submitted.update(
                OrderStatus.PARTIALLY_FILLED, filled_quantity=4, average_fill_price=None
            )

    def test_terminal_cannot_reopen(self):
        rejected = order().update(
            OrderStatus.REJECTED, filled_quantity=0, average_fill_price=None
        )
        with self.assertRaises(ValueError):
            rejected.update(
                OrderStatus.SUBMITTED, filled_quantity=0, average_fill_price=None
            )


if __name__ == "__main__":
    unittest.main()
