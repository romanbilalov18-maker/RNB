from dataclasses import dataclass, field
from typing import Any
from bot.intelligence.core.models.analysis_result import AnalyzerResult


@dataclass(frozen=True)
class Level5Result:
    symbol: str
    score: float
    confidence: float
    consistency: float
    signal_strength: float
    signal_confirmation: float
    signal_conflict: float
    signal_consistency: float
    signal_stability: float
    reliability: float
    analyzer_results: dict[str, AnalyzerResult] = field(default_factory=dict)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
