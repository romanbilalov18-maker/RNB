from dataclasses import dataclass, field
from typing import Any
from bot.intelligence.core.models.analysis_result import AnalyzerResult


@dataclass(frozen=True)
class Level8Result:
    symbol: str
    score: float
    confidence: float
    consistency: float
    market_relative_strength: float
    sector_relative_strength: float
    peer_context: float
    cross_asset_context: float
    benchmark_alignment: float
    relative_consistency: float
    analyzer_results: dict[str, AnalyzerResult] = field(default_factory=dict)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
