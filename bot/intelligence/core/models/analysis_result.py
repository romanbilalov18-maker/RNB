import math
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class AnalyzerResult:
    """Normalized result produced by an intelligence analyzer."""

    analyzer: str
    score: float
    confidence: float
    metrics: Dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.score, (int, float)) or not math.isfinite(self.score) or not 0.0 <= self.score <= 1.0:
            raise ValueError("score must be a finite number between 0 and 1")
        if not isinstance(self.confidence, (int, float)) or not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be a finite number between 0 and 1")
