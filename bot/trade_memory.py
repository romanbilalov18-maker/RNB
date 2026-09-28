from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Literal

Outcome = Literal["WIN", "LOSS", "BREAKEVEN", "OPEN"]

@dataclass(frozen=True)
class TradeDecision:
    timestamp: datetime
    ticker: str
    signal: str
    confidence: float
    reason: str
    quantity: int
    price: float
    features: tuple[float, ...] = ()

@dataclass(frozen=True)
class TradeResult:
    timestamp: datetime
    exit_price: float
    realized_pnl: float

    @property
    def outcome(self) -> Outcome:
        if self.realized_pnl > 0:
            return "WIN"
        if self.realized_pnl < 0:
            return "LOSS"
        return "BREAKEVEN"

@dataclass(frozen=True)
class TradeMemoryRecord:
    decision: TradeDecision
    result: TradeResult | None = None
    error: bool | None = None
    error_reason: str = ""

    @property
    def outcome(self) -> Outcome:
        if self.result is None:
            return "OPEN"
        return self.result.outcome

@dataclass(frozen=True)
class TradeLearningSample:
    timestamp: datetime
    ticker: str
    features: tuple[float, ...]
    signal: str
    confidence: float
    target: int
    outcome: Literal["WIN", "LOSS"]

class TradeMemory:
    """In-memory store for trading decisions and their realized outcomes."""

    def __init__(self) -> None:
        self._records: list[TradeMemoryRecord] = []

    def record_decision(self, decision: TradeDecision) -> TradeMemoryRecord:
        if decision.quantity <= 0 or decision.price <= 0:
            raise ValueError("quantity and price must be positive")
        if not decision.ticker.strip():
            raise ValueError("ticker must not be empty")
        if not 0 <= decision.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        record = TradeMemoryRecord(decision=decision)
        self._records.append(record)
        return record

    def record_result(self, decision_timestamp: datetime, result: TradeResult, *, error: bool | None = None, error_reason: str = "") -> TradeMemoryRecord:
        if result.exit_price <= 0:
            raise ValueError("exit_price must be positive")
        for index, record in enumerate(self._records):
            if record.decision.timestamp == decision_timestamp and record.result is None:
                updated = TradeMemoryRecord(record.decision, result, error, error_reason)
                self._records[index] = updated
                return updated
        raise KeyError("open decision not found")

    def record_exit(self, ticker: str, quantity: int, result: TradeResult, *, error: bool | None = None, error_reason: str = "") -> TradeMemoryRecord:
        """Record a filled exit, including dynamic partial closes."""
        if not ticker.strip():
            raise ValueError("ticker must not be empty")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        for index, record in enumerate(self._records):
            if (
                record.result is None
                and record.decision.ticker == ticker
                and record.decision.signal == "BUY"
            ):
                open_quantity = record.decision.quantity
                if quantity > open_quantity:
                    continue
                if quantity == open_quantity:
                    return self.record_result(
                        record.decision.timestamp, result,
                        error=error, error_reason=error_reason,
                    )

                remaining = open_quantity - quantity
                remaining_decision = TradeDecision(
                    timestamp=record.decision.timestamp,
                    ticker=record.decision.ticker,
                    signal=record.decision.signal,
                    confidence=record.decision.confidence,
                    reason=record.decision.reason,
                    quantity=remaining,
                    price=record.decision.price,
                    features=record.decision.features,
                )
                partial_record = TradeMemoryRecord(
                    decision=TradeDecision(
                        timestamp=result.timestamp,
                        ticker=ticker,
                        signal="SELL",
                        confidence=record.decision.confidence,
                        reason="Partial exit",
                        quantity=quantity,
                        price=result.exit_price,
                        features=record.decision.features,
                    ),
                    result=result,
                    error=error,
                    error_reason=error_reason,
                )
                self._records[index] = TradeMemoryRecord(decision=remaining_decision)
                self._records.append(partial_record)
                return partial_record
        raise KeyError("matching open BUY decision not found")

    def records(self) -> tuple[TradeMemoryRecord, ...]:
        return tuple(self._records)

    def completed(self) -> tuple[TradeMemoryRecord, ...]:
        return tuple(record for record in self._records if record.result is not None)

    def errors(self) -> tuple[TradeMemoryRecord, ...]:
        return tuple(record for record in self._records if record.error is True)

    def training_records(self) -> tuple[TradeMemoryRecord, ...]:
        return tuple(record for record in self._records if record.result is not None and record.error is not None)

    def learning_samples(self, *, feature_count: int, include_breakeven: bool = False) -> tuple[TradeLearningSample, ...]:
        """Export completed entry-time decisions as leakage-safe learning samples."""
        if feature_count <= 0:
            raise ValueError("feature_count must be positive")
        samples: list[TradeLearningSample] = []
        for record in self._records:
            if record.result is None:
                continue
            outcome = record.outcome
            if outcome == "BREAKEVEN" and not include_breakeven:
                continue
            if outcome not in {"WIN", "LOSS"}:
                continue
            features = tuple(record.decision.features)
            if len(features) != feature_count:
                raise ValueError(f"trade features must contain exactly {feature_count} values")
            if any(not isinstance(value, (int, float)) for value in features):
                raise ValueError("trade features must be numeric")
            samples.append(TradeLearningSample(
                timestamp=record.decision.timestamp,
                ticker=record.decision.ticker,
                features=tuple(float(value) for value in features),
                signal=record.decision.signal,
                confidence=record.decision.confidence,
                target=int(outcome == "WIN"),
                outcome=outcome,
            ))
        return tuple(samples)

    def extend(self, records: Iterable[TradeMemoryRecord]) -> None:
        for record in records:
            if record.decision.quantity <= 0 or record.decision.price <= 0:
                raise ValueError("invalid trade decision")
            self._records.append(record)
