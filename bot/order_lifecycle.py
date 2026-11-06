"""Fail-closed order lifecycle model; it does not submit or cancel broker orders."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import math

class OrderStatus(str, Enum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"

_TERMINAL = {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}
_ALLOWED = {
    OrderStatus.CREATED: {OrderStatus.SUBMITTED, OrderStatus.REJECTED, OrderStatus.UNKNOWN},
    OrderStatus.SUBMITTED: {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED,
        OrderStatus.CANCEL_PENDING, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.UNKNOWN},
    OrderStatus.PARTIALLY_FILLED: {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED,
        OrderStatus.CANCEL_PENDING, OrderStatus.CANCELLED, OrderStatus.UNKNOWN},
    OrderStatus.CANCEL_PENDING: {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED,
        OrderStatus.CANCELLED, OrderStatus.UNKNOWN},
    OrderStatus.UNKNOWN: {OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED, OrderStatus.CANCEL_PENDING, OrderStatus.CANCELLED,
        OrderStatus.REJECTED, OrderStatus.UNKNOWN},
}

@dataclass(frozen=True)
class OrderLifecycle:
    client_order_id: str
    requested_quantity: int
    status: OrderStatus = OrderStatus.CREATED
    filled_quantity: int = 0
    average_fill_price: float | None = None

    @property
    def retry_blocked(self) -> bool:
        return self.status not in {OrderStatus.CREATED, OrderStatus.REJECTED, OrderStatus.CANCELLED}

    def update(self, status: OrderStatus, *, filled_quantity: int,
               average_fill_price: float | None) -> "OrderLifecycle":
        if not self.client_order_id.strip():
            raise ValueError("client_order_id is required")
        if isinstance(self.requested_quantity, bool) or not isinstance(self.requested_quantity, int) or self.requested_quantity <= 0:
            raise ValueError("requested_quantity must be positive")
        if isinstance(filled_quantity, bool) or not isinstance(filled_quantity, int):
            raise ValueError("filled_quantity must be an integer")
        if not 0 <= filled_quantity <= self.requested_quantity:
            raise ValueError("filled_quantity is outside requested quantity")
        if self.status in _TERMINAL:
            raise ValueError("terminal order status cannot transition")
        if status not in _ALLOWED.get(self.status, set()):
            raise ValueError(f"invalid order transition: {self.status.value} -> {status.value}")
        if status == OrderStatus.PARTIALLY_FILLED and not 0 < filled_quantity < self.requested_quantity:
            raise ValueError("partial fill must be between zero and requested quantity")
        if status == OrderStatus.FILLED and filled_quantity != self.requested_quantity:
            raise ValueError("filled status requires full requested quantity")
        if filled_quantity > 0:
            if isinstance(average_fill_price, bool) or not isinstance(average_fill_price, (int, float)) or not math.isfinite(average_fill_price) or average_fill_price <= 0:
                raise ValueError("actual average fill price must be finite and positive")
        elif average_fill_price is not None:
            raise ValueError("fill price must be absent when filled quantity is zero")
        if filled_quantity < self.filled_quantity:
            raise ValueError("cumulative filled quantity cannot decrease")
        return OrderLifecycle(self.client_order_id, self.requested_quantity, status,
            filled_quantity, float(average_fill_price) if average_fill_price is not None else None)
