from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result
from .analyzers import momentum_structure, price_structure, relative_strength, signal_conflict, trend, volume_flow
from .models.level_02_result import Level2Result


ANALYZERS = (trend, momentum_structure, volume_flow, price_structure, relative_strength, signal_conflict)
WEIGHTS = (0.20, 0.18, 0.18, 0.16, 0.14, 0.14)


def analyze(snapshot: MarketSnapshot, level1: Level1Result) -> Level2Result:
    """Analyze the snapshot using Level 1 evidence while preserving missingness."""
    results = tuple(module.analyze(snapshot, level1) for module in ANALYZERS)
    effective_weights = [weight * result.confidence for result, weight in zip(results, WEIGHTS)]
    total_effective_weight = sum(effective_weights)
    score = (
        sum(result.score * weight for result, weight in zip(results, effective_weights)) / total_effective_weight
        if total_effective_weight > 0
        else 0.0
    )
    confidence = sum(result.confidence * weight for result, weight in zip(results, WEIGHTS))
    consistency_result = next(r for r in results if r.analyzer == "signal_conflict")
    consistency = consistency_result.score
    strengths = tuple(r.analyzer for r in results if r.confidence > 0 and r.score >= 0.70)
    weaknesses = tuple(r.analyzer for r in results if r.confidence > 0 and r.score <= 0.30)
    warnings = tuple(dict.fromkeys(
        (*level1.warnings, *(warning for result in results for warning in result.warnings))
    ))
    if total_effective_weight <= 0:
        warnings = tuple(dict.fromkeys((*warnings, "level_02_no_confident_analyzer_results")))
    return Level2Result(
        symbol=snapshot.symbol,
        score=score,
        confidence=confidence,
        consistency=consistency,
        analyzer_results=results,
        strengths=strengths,
        weaknesses=weaknesses,
        warnings=warnings,
        metadata={
            "version": "1.1",
            "weights": dict(zip((r.analyzer for r in results), WEIGHTS)),
            "effective_weights": dict(zip((r.analyzer for r in results), effective_weights)),
            "level1_confidence": level1.confidence,
            "level1_consistency": level1.consistency,
            "relative_strength_source": "snapshot.relative_market_return",
            "signal_conflict_semantics": "score_dispersion_proxy_not_directional_conflict",
        },
    )
