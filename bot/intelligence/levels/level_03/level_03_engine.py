import math

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result
from .analyzers import correlation_context, macro_context, market_regime, market_strength, relative_market, sector_context
from .models.level_03_result import Level3Result


ANALYZERS = (market_regime, market_strength, sector_context, relative_market, correlation_context, macro_context)
WEIGHTS = (0.22, 0.20, 0.16, 0.18, 0.12, 0.12)


def analyze(snapshot: MarketSnapshot, level2: Level2Result) -> Level3Result:
    """Analyze market context using the matching Level 2 result and observed snapshot data."""
    if level2.symbol != snapshot.symbol:
        raise ValueError(
            f"Level 2 symbol {level2.symbol!r} does not match snapshot symbol {snapshot.symbol!r}"
        )

    results = tuple(module.analyze(snapshot, level2) for module in ANALYZERS)
    # Confidence is a weight only when it is a valid finite number in [0, 1].
    confidences = []
    for result in results:
        value = result.confidence
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Analyzer {result.analyzer!r} returned invalid confidence")
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"Analyzer {result.analyzer!r} confidence must be between 0 and 1")
        confidences.append(value)

    effective_weights = [weight * confidence for weight, confidence in zip(WEIGHTS, confidences)]
    total_effective_weight = sum(effective_weights)
    score = (
        sum(result.score * weight for result, weight in zip(results, effective_weights)) / total_effective_weight
        if total_effective_weight > 0 else 0.0
    )
    confidence = sum(weight * value for weight, value in zip(WEIGHTS, confidences))
    strengths = tuple(r.analyzer for r in results if r.confidence > 0 and r.score >= 0.70)
    weaknesses = tuple(r.analyzer for r in results if r.confidence > 0 and r.score <= 0.30)
    warnings = tuple(dict.fromkeys((*level2.warnings, *(w for r in results for w in r.warnings)))

    return Level3Result(
        symbol=snapshot.symbol,
        score=score,
        confidence=confidence,
        # Preserve Level 2's published consistency value; do not reinterpret its
        # signal-dispersion proxy as a new directional-conflict assessment.
        consistency=level2.consistency,
        analyzer_results=results,
        strengths=strengths,
        weaknesses=weaknesses,
        warnings=warnings,
        metadata={
            "version": "1.1",
            "weights": dict(zip((r.analyzer for r in results), WEIGHTS)),
            "effective_weights": dict(zip((r.analyzer for r in results), effective_weights)),
            "level2_confidence": level2.confidence,
            "level2_consistency_source": "level2.consistency",
            "level2_consistency_semantics": level2.metadata.get(
                "signal_conflict_semantics", "upstream_consistency_semantics_unspecified"
            ),
            "analyzers_with_evidence": [r.analyzer for r in results if r.confidence > 0],
            "analyzers_without_evidence": [r.analyzer for r in results if r.confidence == 0],
        },
    )
