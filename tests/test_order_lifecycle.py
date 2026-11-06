import pytest
from bot.order_lifecycle import OrderLifecycle, OrderStatus

def order():
    return OrderLifecycle("rnb-uuid", requested_quantity=10)

def test_partial_then_full_fill():
    partial = order().update(OrderStatus.SUBMITTED, filled_quantity=0, average_fill_price=None).update(
        OrderStatus.PARTIALLY_FILLED, filled_quantity=4, average_fill_price=101.25)
    assert partial.retry_blocked
    filled = partial.update(OrderStatus.FILLED, filled_quantity=10, average_fill_price=101.5)
    assert filled.filled_quantity == 10
    assert filled.average_fill_price == 101.5

def test_unknown_blocks_resubmission_until_reconciled():
    unknown = order().update(OrderStatus.UNKNOWN, filled_quantity=0, average_fill_price=None)
    assert unknown.retry_blocked
    assert unknown.update(OrderStatus.SUBMITTED, filled_quantity=0, average_fill_price=None).retry_blocked

def test_fill_requires_quantity_and_price():
    submitted = order().update(OrderStatus.SUBMITTED, filled_quantity=0, average_fill_price=None)
    with pytest.raises(ValueError):
        submitted.update(OrderStatus.FILLED, filled_quantity=5, average_fill_price=100)
    with pytest.raises(ValueError):
        submitted.update(OrderStatus.PARTIALLY_FILLED, filled_quantity=4, average_fill_price=None)

def test_terminal_cannot_reopen():
    rejected = order().update(OrderStatus.REJECTED, filled_quantity=0, average_fill_price=None)
    with pytest.raises(ValueError):
        rejected.update(OrderStatus.SUBMITTED, filled_quantity=0, average_fill_price=None)
