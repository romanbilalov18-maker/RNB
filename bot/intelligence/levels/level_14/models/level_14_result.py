from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

from bot.intelligence.core.models.analysis_result import AnalyzerResult


@dataclass(frozen=True)
class Level14Result:
    """Adversarial profile that challenges strong signals without making a trade decision."""

    symbol: str
    score: float
    confidence: float
    consistency: float
    signal_contradiction: float
    conviction_trap: float
    risk_contradiction: float
    anomaly_contradiction: float
    scenario_contradiction: float
    data_reliability: float
    analyzer_results: Tuple[AnalyzerResult, ...] = ()
    strengths: Tuple[str, ...] = ()
    weaknesses: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "score", "confidence", "consistency", "signal_contradiction",
            "conviction_trap", "risk_contradiction", "anomaly_contradiction",
            "scenario_contradiction", "data_reliability",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
