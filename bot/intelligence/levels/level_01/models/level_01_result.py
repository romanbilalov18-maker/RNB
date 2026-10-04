from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

from bot.intelligence.core.models.analysis_result import AnalyzerResult


@dataclass(frozen=True)
class Level1Result:
    """Stable output contract for Level 1 consumed by later levels."""

    symbol: str
    score: float
    confidence: float
    consistency: float
    analyzer_results: Tuple[AnalyzerResult, ...] = ()
    strengths: Tuple[str, ...] = ()
    weaknesses: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (
            ("score", self.score),
            ("confidence", self.confidence),
            ("consistency", self.consistency),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
