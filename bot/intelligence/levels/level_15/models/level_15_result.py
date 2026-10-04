from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

from bot.intelligence.core.models.analysis_result import AnalyzerResult


@dataclass(frozen=True)
class Level15Result:
    """Master intelligence synthesis; not a trading decision."""

    symbol: str
    score: float
    confidence: float
    consistency: float
    signal_quality: float
    risk_quality: float
    scenario_quality: float
    anomaly_quality: float
    adversarial_resilience: float
    learning_quality: float
    master_confidence: float
    analyzer_results: Tuple[AnalyzerResult, ...] = ()
    strengths: Tuple[str, ...] = ()
    weaknesses: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "score", "confidence", "consistency", "signal_quality",
            "risk_quality", "scenario_quality", "anomaly_quality",
            "adversarial_resilience", "learning_quality", "master_confidence",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
