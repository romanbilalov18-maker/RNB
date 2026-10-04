from dataclasses import dataclass, field
from typing import Any
from bot.intelligence.core.models.analysis_result import AnalyzerResult


@dataclass(frozen=True)
class Level4Result:
    symbol: str
    score: float
    confidence: float
    consistency: float
    buying_pressure: float
    selling_pressure: float
    pressure_balance: float
    accumulation: float
    distribution: float
    abnormal_activity: float
    liquidity_behavior: float
    analyzer_results: dict[str, AnalyzerResult] = field(default_factory=dict)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
