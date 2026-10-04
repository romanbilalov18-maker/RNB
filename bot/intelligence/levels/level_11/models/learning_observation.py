from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass(frozen=True)
class LearningObservation:
    """Historical outcome used for learning without mutating trading state."""

    outcome_return: float
    correct: bool
    level_scores: Dict[str, float] = field(default_factory=dict)
    analyzer_scores: Dict[str, float] = field(default_factory=dict)
    regime: Optional[str] = None

    def __post_init__(self) -> None:
        for name, mapping in (("level_scores", self.level_scores), ("analyzer_scores", self.analyzer_scores)):
            for key, value in mapping.items():
                if not 0.0 <= value <= 1.0:
                    raise ValueError(f"{name}[{key}] must be between 0 and 1")
