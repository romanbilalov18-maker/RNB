from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

from bot.intelligence.core.models.analysis_result import AnalyzerResult


@dataclass(frozen=True)
class Level13Result:
    """Scenario forecast profile; describes plausible paths without predicting certainty."""

    symbol: str
    score: float
    confidence: float
    consistency: float
    continuation: float
    reversal: float
    volatility_expansion: float
    adverse_scenario: float
    neutral_scenario: float
    scenario_confidence: float
    analyzer_results: Tuple[AnalyzerResult, ...] = ()
    strengths: Tuple[str, ...] = ()
    weaknesses: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "score", "confidence", "consistency", "continuation", "reversal",
            "volatility_expansion", "adverse_scenario", "neutral_scenario",
            "scenario_confidence",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
