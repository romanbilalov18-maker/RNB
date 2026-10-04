from dataclasses import dataclass, field
from typing import Any
from bot.intelligence.core.models.analysis_result import AnalyzerResult


@dataclass(frozen=True)
class Level7Result:
    symbol: str
    score: float
    confidence: float
    consistency: float
    momentum_acceleration: float
    trend_persistence: float
    movement_exhaustion: float
    regime_transition: float
    temporal_anomaly: float
    dynamic_stability: float
    analyzer_results: dict[str, AnalyzerResult] = field(default_factory=dict)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
