"""Read-only snapshot of a T-Invest brokerage account.

This module deliberately contains no order-placement or account-mutation calls.
It is a foundation for reconciliation; it must not be used to authorize trading.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


class BrokerSnapshotError(RuntimeError):
    """Broker account data is missing, malformed, or internally inconsistent."""


@dataclass(frozen=True)
class BrokerPosition:
    instrument_uid: str
    ticker: str
    quantity: float
    current_price: float
    currency: str


@dataclass(frozen=True)
class BrokerAccountSnapshot:
    account_id: str
    currency: str
    available_cash: float
    blocked_cash: float
    positions: tuple[BrokerPosition, ...]
    open_orders_count: int

    @property
    def total_position_value(self) -> float:
        return sum(position.quantity * position.current_price for position in self.positions)

    @property
    def total_equity(self) -> float:
        return self.available_cash + self.blocked_cash + self.total_position_value


def _number(value: Any, label: str, *, allow_zero: bool = True) -> float:
    """Convert SDK quotation/money values or plain numbers to finite floats."""
    if value is None:
        raise BrokerSnapshotError(f"{label} is missing")
    if isinstance(value, bool):
        raise BrokerSnapshotError(f"{label} must be numeric, not boolean")
    if hasattr(value, "units") and hasattr(value, "nano"):
        units = getattr(value, "units")
        nano = getattr(value, "nano")
        if isinstance(units, bool) or isinstance(nano, bool):
            raise BrokerSnapshotError(f"{label} must be numeric, not boolean")
        try:
            value = float(units) + float(nano) / 1_000_000_000
        except (TypeError, ValueError, OverflowError) as exc:
            raise BrokerSnapshotError(f"{label} is not numeric") from exc
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise BrokerSnapshotError(f"{label} is not numeric") from exc
    if not math.isfinite(result) or (result < 0 if allow_zero else result <= 0):
        qualifier = "finite and non-negative" if allow_zero else "finite and positive"
        raise BrokerSnapshotError(f"{label} must be {qualifier}")
    return result


def _currency(value: Any, label: str) -> str:
    result = str(value or "").strip().upper()
    if not result:
        raise BrokerSnapshotError(f"{label} is missing")
    return result


def _required_text(value: Any, label: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise BrokerSnapshotError(f"{label} is missing")
    return result


class TInvestAccountReader:
    """Read account identity, portfolio, and open orders from an injected SDK client.

    Expected SDK surface: users.get_accounts(), operations.get_portfolio(),
    and orders.get_orders(). A client is injected to make this layer testable
    without network access. No order creation/cancellation APIs are called.
    """

    def __init__(self, client: Any):
        self._client = client

    def read_snapshot(self, account_id: str) -> BrokerAccountSnapshot:
        account_id = _required_text(account_id, "account_id")
        accounts_response = self._client.users.get_accounts()
        accounts = list(getattr(accounts_response, "accounts", ()) or ())
        matched = [
            account for account in accounts
            if str(getattr(account, "id", "") or "").strip() == account_id
        ]
        if len(matched) != 1:
            raise BrokerSnapshotError(
                f"account_id must resolve to exactly one accessible account; "
                f"matches={len(matched)}"
            )

        portfolio_response = self._client.operations.get_portfolio(account_id=account_id)
        portfolio = getattr(portfolio_response, "portfolio", portfolio_response)
        money = list(getattr(portfolio, "money", ()) or ())
        if len(money) != 1:
            # This initial version intentionally refuses to guess a currency or
            # combine balances from multiple currencies.
            raise BrokerSnapshotError(
                f"portfolio must contain exactly one cash currency; found={len(money)}"
            )
        cash_item = money[0]
        currency = _currency(getattr(cash_item, "currency", None), "cash currency")
        available_cash = _number(getattr(cash_item, "available", None), "available cash")
        blocked_cash = _number(getattr(cash_item, "blocked", 0), "blocked cash")

        positions = []
        seen_uids: set[str] = set()
        for item in list(getattr(portfolio, "securities", ()) or ()):
            uid = _required_text(
                getattr(item, "instrument_uid", None) or getattr(item, "figi", None),
                "position instrument_uid",
            )
            if uid in seen_uids:
                raise BrokerSnapshotError(f"duplicate broker position instrument: {uid}")
            seen_uids.add(uid)
            quantity = _number(getattr(item, "quantity", None), f"position {uid} quantity")
            if quantity <= 0:
                # Broker responses can include zero-quantity rows; omit them.
                continue
            ticker = _required_text(getattr(item, "ticker", None), f"position {uid} ticker")
            price = _number(
                getattr(item, "current_price", None),
                f"position {uid} current_price",
            )
            if price <= 0:
                raise BrokerSnapshotError(f"position {uid} current_price must be positive")
            position_currency = _currency(
                getattr(item, "currency", None), f"position {uid} currency"
            )
            if position_currency != currency:
                raise BrokerSnapshotError(
                    f"position {uid} currency {position_currency} differs from "
                    f"account cash currency {currency}; multi-currency reconciliation "
                    "is not supported by this snapshot"
                )
            positions.append(BrokerPosition(uid, ticker, quantity, price, position_currency))

        orders_response = self._client.orders.get_orders(account_id=account_id)
        orders = list(getattr(orders_response, "orders", ()) or ())
        active_orders = [
            order for order in orders
            if str(getattr(getattr(order, "execution_report_status", None), "name", "")
                   or getattr(order, "execution_report_status", "")).upper()
            not in {"EXECUTION_REPORT_STATUS_FILL", "EXECUTION_REPORT_STATUS_CANCELLED",
                    "EXECUTION_REPORT_STATUS_REJECTED", "FILL", "CANCELLED", "REJECTED"}
        ]

        return BrokerAccountSnapshot(
            account_id=account_id,
            currency=currency,
            available_cash=available_cash,
            blocked_cash=blocked_cash,
            positions=tuple(positions),
            open_orders_count=len(active_orders),
        )
