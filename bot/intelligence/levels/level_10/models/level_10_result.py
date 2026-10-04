from dataclasses import dataclass, field
from typing import Any
from bot.intelligence.core.models.analysis_result import AnalyzerResult


@dataclass(frozen=True)
class Level10Result:
    symbol: str
    score: float
    confidence: float
    consistency: float
    conviction: float
    cross_level_agreement: float
    confidence_quality: float
    risk_adjusted_conviction: float
    warning_impact: float
    decision_readiness: float
    analyzer_results: dict[str, AnalyzerResult] = field(default_factory=dict)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
