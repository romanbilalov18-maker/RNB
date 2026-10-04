from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

from bot.intelligence.core.models.analysis_result import AnalyzerResult


@dataclass(frozen=True)
class Level11Result:
    """Learning profile and adaptation recommendations; never a trade decision."""

    symbol: str
    score: float
    confidence: float
    consistency: float
    outcome_quality: float
    level_effectiveness: float
    analyzer_effectiveness: float
    regime_adaptation: float
    weight_adaptation: float
    learning_confidence: float
    sample_count: int
    proposed_level_weights: Dict[str, float] = field(default_factory=dict)
    proposed_analyzer_weights: Dict[str, float] = field(default_factory=dict)
    analyzer_results: Tuple[AnalyzerResult, ...] = ()
    strengths: Tuple[str, ...] = ()
    weaknesses: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "score", "confidence", "consistency", "outcome_quality",
            "level_effectiveness", "analyzer_effectiveness",
            "regime_adaptation", "weight_adaptation", "learning_confidence",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.sample_count < 0:
            raise ValueError("sample_count must be non-negative")
