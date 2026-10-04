from dataclasses import dataclass, field
from typing import Any
from bot.intelligence.core.models.analysis_result import AnalyzerResult


@dataclass(frozen=True)
class Level9Result:
    symbol: str
    score: float
    confidence: float
    consistency: float
    concentration_risk: float
    diversification_value: float
    portfolio_compatibility: float
    correlation_risk: float
    opportunity_priority: float
    portfolio_consistency: float
    analyzer_results: dict[str, AnalyzerResult] = field(default_factory=dict)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
