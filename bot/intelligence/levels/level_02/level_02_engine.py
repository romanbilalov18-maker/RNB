from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result
from .analyzers import momentum_structure, price_structure, relative_strength, signal_conflict, trend, volume_flow
from .models.level_02_result import Level2Result


ANALYZERS = (trend, momentum_structure, volume_flow, price_structure, relative_strength, signal_conflict)
WEIGHTS = (0.20, 0.18, 0.18, 0.16, 0.14, 0.14)


def analyze(snapshot: MarketSnapshot, level1: Level1Result) -> Level2Result:
    results = tuple(module.analyze(snapshot, level1) for module in ANALYZERS)
    score = sum(result.score * weight for result, weight in zip(results, WEIGHTS))
    confidence = sum(result.confidence * weight for result, weight in zip(results, WEIGHTS))
    consistency_result = next(r for r in results if r.analyzer == "signal_conflict")
    consistency = consistency_result.score
    strengths = tuple(r.analyzer for r in results if r.score >= 0.70)
    weaknesses = tuple(r.analyzer for r in results if r.score <= 0.30)
    warnings = tuple(w for r in results for w in r.warnings)
    return Level2Result(
        symbol=snapshot.symbol,
        score=score,
        confidence=confidence,
        consistency=consistency,
        analyzer_results=results,
        strengths=strengths,
        weaknesses=weaknesses,
        warnings=warnings,
        metadata={"version": "1.0", "weights": dict(zip((r.analyzer for r in results), WEIGHTS))},
    )
