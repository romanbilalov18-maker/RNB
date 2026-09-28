from dataclasses import dataclass
from typing import Iterable, Literal

from bot.models import SignalResult

Decision = Literal["BUY", "SELL", "HOLD"]


@dataclass(frozen=True)
class DecisionInput:
    source: str
    result: SignalResult
    weight: float = 1.0


@dataclass(frozen=True)
class MetaDecision:
    signal: Decision
    confidence: float
    reason: str
    contributors: tuple[str, ...]


class MetaDecisionEngine:
    """Combines independent model/strategy signals without executing trades."""

    def __init__(self, min_confidence: float = 0.5) -> None:
        if not 0 <= min_confidence <= 1:
            raise ValueError("min_confidence must be between 0 and 1")
        self.min_confidence = min_confidence

    def decide(self, inputs: Iterable[DecisionInput]) -> MetaDecision:
        items = tuple(inputs)
        if not items:
            raise ValueError("at least one decision input is required")

        for item in items:
            if not item.source.strip():
                raise ValueError("decision source must not be empty")
            if item.weight <= 0:
                raise ValueError("decision weight must be positive")
            if not 0 <= item.result.confidence <= 1:
                raise ValueError("signal confidence must be between 0 and 1")

        scores = {"BUY": 0.0, "SELL": 0.0, "HOLD": 0.0}
        weighted_confidence = {"BUY": 0.0, "SELL": 0.0, "HOLD": 0.0}

        for item in items:
            signal = item.result.signal
            scores[signal] += item.weight
            weighted_confidence[signal] += item.weight * item.result.confidence

        highest = max(scores.values())
        winners = [signal for signal, score in scores.items() if score == highest]

        if len(winners) != 1:
            return MetaDecision(
                signal="HOLD",
                confidence=0.0,
                reason="No unique meta-decision consensus",
                contributors=tuple(item.source for item in items),
            )

        signal = winners[0]
        confidence = weighted_confidence[signal] / scores[signal]
        if confidence < self.min_confidence:
            return MetaDecision(
                signal="HOLD",
                confidence=confidence,
                reason=f"Consensus confidence below threshold {self.min_confidence:.2f}",
                contributors=tuple(
                    item.source for item in items if item.result.signal == signal
                ),
            )

        contributors = tuple(
            item.source for item in items if item.result.signal == signal
        )
        return MetaDecision(
            signal=signal,
            confidence=confidence,
            reason=f"Meta consensus from {len(contributors)}/{len(items)} inputs",
            contributors=contributors,
        )
