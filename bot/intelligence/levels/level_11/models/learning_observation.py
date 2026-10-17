from dataclasses import dataclass, field
import math
from numbers import Real
from typing import Dict, Optional


@dataclass(frozen=True)
class LearningObservation:
    """Historical outcome used for learning without mutating trading state."""

    outcome_return: float
    correct: bool
    level_scores: Dict[str, float] = field(default_factory=dict)
    analyzer_scores: Dict[str, float] = field(default_factory=dict)
    regime: Optional[str] = None
    decision_time: Optional[str] = None
    outcome_target_date: Optional[str] = None
    realized_trade_return: Optional[float] = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.outcome_return, bool)
            or not isinstance(self.outcome_return, Real)
            or not math.isfinite(self.outcome_return)
        ):
            raise ValueError("outcome_return must be a finite number")

        if not isinstance(self.correct, bool):
            raise ValueError("correct must be a bool")

        for name, mapping in (
            ("level_scores", self.level_scores),
            ("analyzer_scores", self.analyzer_scores),
        ):
            if not isinstance(mapping, dict):
                raise ValueError(f"{name} must be a dictionary")
            for key, value in mapping.items():
                if not isinstance(key, str) or not key.strip():
                    raise ValueError(f"{name} keys must be non-empty strings")
                if (
                    isinstance(value, bool)
                    or not isinstance(value, Real)
                    or not math.isfinite(value)
                    or not 0.0 <= value <= 1.0
                ):
                    raise ValueError(f"{name}[{key}] must be a finite number between 0 and 1")

        if self.realized_trade_return is not None and (
            isinstance(self.realized_trade_return, bool)
            or not isinstance(self.realized_trade_return, Real)
            or not math.isfinite(self.realized_trade_return)
        ):
            raise ValueError("realized_trade_return must be None or a finite number")

        for name in ("regime", "decision_time", "outcome_target_date"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be None or a non-empty string")
