from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

from bot.intelligence.core.models.analysis_result import AnalyzerResult


@dataclass(frozen=True)
class Level12Result:
    """Anomaly profile; detects unusual conditions without creating a trade decision."""

    symbol: str
    score: float
    confidence: float
    consistency: float
    price_anomaly: float
    volume_anomaly: float
    volatility_anomaly: float
    behavior_anomaly: float
    signal_anomaly: float
    data_anomaly: float
    analyzer_results: Tuple[AnalyzerResult, ...] = ()
    strengths: Tuple[str, ...] = ()
    weaknesses: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "score", "confidence", "consistency", "price_anomaly",
            "volume_anomaly", "volatility_anomaly", "behavior_anomaly",
            "signal_anomaly", "data_anomaly",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
