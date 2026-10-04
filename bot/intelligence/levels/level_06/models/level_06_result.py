from dataclasses import dataclass, field
from typing import Any
from bot.intelligence.core.models.analysis_result import AnalyzerResult


@dataclass(frozen=True)
class Level6Result:
    symbol: str
    score: float
    confidence: float
    consistency: float
    downside_risk: float
    volatility_risk: float
    reward_potential: float
    risk_reward: float
    adverse_scenario: float
    risk_consistency: float
    analyzer_results: dict[str, AnalyzerResult] = field(default_factory=dict)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
