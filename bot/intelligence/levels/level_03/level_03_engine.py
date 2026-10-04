from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result
from .analyzers import correlation_context, macro_context, market_regime, market_strength, relative_market, sector_context
from .models.level_03_result import Level3Result


ANALYZERS = (market_regime, market_strength, sector_context, relative_market, correlation_context, macro_context)
WEIGHTS = (0.22, 0.20, 0.16, 0.18, 0.12, 0.12)


def analyze(snapshot: MarketSnapshot, level2: Level2Result) -> Level3Result:
    results = tuple(module.analyze(snapshot, level2) for module in ANALYZERS)
    score = sum(result.score * weight for result, weight in zip(results, WEIGHTS))
    confidence = sum(result.confidence * weight for result, weight in zip(results, WEIGHTS))
    consistency = next((r.score for r in level2.analyzer_results if r.analyzer == "signal_conflict"), level2.consistency)
    strengths = tuple(r.analyzer for r in results if r.score >= 0.70)
    weaknesses = tuple(r.analyzer for r in results if r.score <= 0.30)
    warnings = tuple(w for r in results for w in r.warnings)
    return Level3Result(
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
