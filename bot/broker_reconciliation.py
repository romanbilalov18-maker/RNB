"""Compare a read-only broker snapshot with a separately maintained broker ledger.

This is intentionally independent from the RNB virtual portfolio: a virtual balance
must never be treated as the expected real-broker balance. The result is diagnostic
only and never authorizes orders.
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


def reconcile_broker_snapshot(
    actual: BrokerAccountSnapshot,
    expected: BrokerLedgerSnapshot,
    *,
    cash_tolerance: float = 0.01,
    quantity_tolerance: float = 1e-8,
) -> BrokerReconciliationReport:
    """Report differences; fail closed on invalid tolerances or account mismatch."""
    for label, tolerance in (
        ("cash_tolerance", cash_tolerance),
        ("quantity_tolerance", quantity_tolerance),
    ):
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)):
            raise ValueError(f"{label} must be a finite non-negative number")
        if not math.isfinite(tolerance) or tolerance < 0:
            raise ValueError(f"{label} must be a finite non-negative number")

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
        if (
            isinstance(expected_value, bool)
            or not isinstance(expected_value, (int, float))
            or not math.isfinite(expected_value)
            or expected_value < 0
        ):
            raise ValueError(f"expected {field} must be finite and non-negative")
        if abs(actual_value - expected_value) > cash_tolerance:
            differences.append(ReconciliationDifference(
                field, float(expected_value), float(actual_value),
                f"difference exceeds tolerance {cash_tolerance}",
            ))

    actual_positions = {position.instrument_uid: position.quantity for position in actual.positions}
    expected_positions = dict(expected.positions_by_uid)
    for uid in sorted(set(actual_positions) | set(expected_positions)):
        expected_quantity = expected_positions.get(uid, 0.0)
        actual_quantity = actual_positions.get(uid, 0.0)
        if (
            isinstance(expected_quantity, bool)
            or not isinstance(expected_quantity, (int, float))
            or not math.isfinite(expected_quantity)
            or expected_quantity < 0
        ):
            raise ValueError(f"expected quantity for {uid} must be finite and non-negative")
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
