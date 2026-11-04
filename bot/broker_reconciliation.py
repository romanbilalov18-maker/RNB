"""Compare a read-only broker snapshot with a separately maintained broker ledger.

This is intentionally independent from the RNB virtual portfolio: a virtual balance
must never be treated as the expected real-broker balance. The result is diagnostic
only and never authorizes trading.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from bot.broker_account_snapshot import BrokerAccountSnapshot


@dataclass(frozen=True)
class BrokerLedgerSnapshot:
    account_id: str
    currency: str
    available_cash: float
    blocked_cash: float
    positions_by_uid: Mapping[str, float]


@dataclass(frozen=True)
class ReconciliationDifference:
    field: str
    expected: float | str
    actual: float | str
    detail: str


@dataclass(frozen=True)
class BrokerReconciliationReport:
    account_id: str
    matched: bool
    differences: tuple[ReconciliationDifference, ...]
    blockers: tuple[str, ...]


def _validate_non_negative_number(value: object, label: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{label} must be finite and non-negative")


def reconcile_broker_snapshot(
    actual: BrokerAccountSnapshot,
    expected: BrokerLedgerSnapshot,
    *,
    cash_tolerance: float = 0.01,
    quantity_tolerance: float = 1e-8,
) -> BrokerReconciliationReport:
    """Report differences; reject malformed snapshots rather than compare partial data."""
    for label, tolerance in (
        ("cash_tolerance", cash_tolerance),
        ("quantity_tolerance", quantity_tolerance),
    ):
        _validate_non_negative_number(tolerance, label)

    for label, value in (
        ("actual available_cash", actual.available_cash),
        ("actual blocked_cash", actual.blocked_cash),
        ("expected available_cash", expected.available_cash),
        ("expected blocked_cash", expected.blocked_cash),
    ):
        _validate_non_negative_number(value, label)

    if not isinstance(actual.open_orders_count, int) or isinstance(actual.open_orders_count, bool) or actual.open_orders_count < 0:
        raise ValueError("actual open_orders_count must be a non-negative integer")

    actual_positions: dict[str, float] = {}
    for position in actual.positions:
        uid = str(position.instrument_uid or "").strip()
        if not uid:
            raise ValueError("actual position instrument_uid must be non-empty")
        if uid in actual_positions:
            raise ValueError(f"duplicate actual position instrument_uid: {uid}")
        _validate_non_negative_number(position.quantity, f"actual quantity for {uid}")
        actual_positions[uid] = position.quantity

    if not str(actual.account_id or "").strip() or not str(expected.account_id or "").strip():
        raise ValueError("account_id must be non-empty")
    if not str(actual.currency or "").strip() or not str(expected.currency or "").strip():
        raise ValueError("currency must be non-empty")

    differences: list[ReconciliationDifference] = []
    blockers: list[str] = []
    if actual.account_id != expected.account_id:
        differences.append(ReconciliationDifference(
            "account_id", expected.account_id, actual.account_id, "account identifiers differ"
        ))
        blockers.append("account identity mismatch")
    if actual.currency.upper() != expected.currency.upper():
        differences.append(ReconciliationDifference(
            "currency", expected.currency.upper(), actual.currency.upper(),
            "account currencies differ; currency conversion is not performed",
        ))
        blockers.append("account currency mismatch")

    for field in ("available_cash", "blocked_cash"):
        expected_value = getattr(expected, field)
        actual_value = getattr(actual, field)
        if abs(actual_value - expected_value) > cash_tolerance:
            differences.append(ReconciliationDifference(
                field, float(expected_value), float(actual_value),
                f"difference exceeds tolerance {cash_tolerance}",
            ))

    expected_positions = dict(expected.positions_by_uid)
    for uid, quantity in expected_positions.items():
        if not str(uid or "").strip():
            raise ValueError("expected position instrument_uid must be non-empty")
        _validate_non_negative_number(quantity, f"expected quantity for {uid}")

    for uid in sorted(set(actual_positions) | set(expected_positions)):
        expected_quantity = expected_positions.get(uid, 0.0)
        actual_quantity = actual_positions.get(uid, 0.0)
        if abs(actual_quantity - expected_quantity) > quantity_tolerance:
            differences.append(ReconciliationDifference(
                f"position:{uid}", float(expected_quantity), float(actual_quantity),
                f"quantity difference exceeds tolerance {quantity_tolerance}",
            ))

    # Existing open orders can change available funds or positions after this snapshot.
    if actual.open_orders_count:
        blockers.append(f"{actual.open_orders_count} open/unresolved broker order(s)")
    if differences:
        blockers.append("broker ledger does not match current broker snapshot")

    return BrokerReconciliationReport(
        account_id=actual.account_id,
        matched=not differences and not blockers,
        differences=tuple(differences),
        blockers=tuple(blockers),
    )
