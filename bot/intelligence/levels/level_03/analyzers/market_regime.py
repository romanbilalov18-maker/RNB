from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


REGIME_MIDPOINT = 0.5


def _classify_regime(trend_score: float, structure_score: float) -> str:
    """Classify only when trend and price structure agree directionally.

    Both upstream scores are centered on 0.5: values above/below the midpoint
    indicate positive/negative directional evidence. A disagreement, including
    one neutral input, is deliberately classified as mixed rather than forcing
    a bullish/bearish label. These are semantic score bands, not fitted market
    thresholds or a claim of predictive calibration.
    """
    trend_direction = (trend_score > REGIME_MIDPOINT) - (trend_score < REGIME_MIDPOINT)
    structure_direction = (
        (structure_score > REGIME_MIDPOINT) - (structure_score < REGIME_MIDPOINT)
    )
    if trend_direction == 0 and structure_direction == 0:
        return "neutral"
    if trend_direction > 0 and structure_direction > 0:
        return "bullish"
    if trend_direction < 0 and structure_direction < 0:
        return "bearish"
    return "mixed"


def analyze(snapshot: MarketSnapshot, level2: Level2Result) -> AnalyzerResult:
    results = {
        result.analyzer: result
        for result in level2.analyzer_results
        if result.analyzer in {"trend", "price_structure"} and result.confidence > 0
    }
    weights = {"trend": 0.65, "price_structure": 0.35}
    effective = {name: weights[name] * result.confidence for name, result in results.items()}
    total = sum(effective.values())
    if total <= 0:
        return AnalyzerResult(
            "market_regime", 0.0, 0.0,
            {"available_inputs": [], "regime": None, "regime_method": "directional_consensus_midpoint_v1"},
            ("market_regime_inputs_unavailable",),
        )

    score = sum(results[name].score * effective[name] for name in results) / total
    confidence = sum(effective.values()) / sum(weights[name] for name in results)
    trend_score = results["trend"].score if "trend" in results else None
    structure_score = results["price_structure"].score if "price_structure" in results else None
    regime = (
        _classify_regime(trend_score, structure_score)
        if trend_score is not None and structure_score is not None
        else None
    )
    warnings = () if regime is not None else ("market_regime_consensus_inputs_incomplete",)
    return AnalyzerResult(
        "market_regime",
        score,
        min(1.0, confidence),
        {
            "trend_score": trend_score,
            "structure_score": structure_score,
            "available_inputs": list(results),
            "regime": regime,
            "regime_method": "directional_consensus_midpoint_v1",
            "regime_threshold": REGIME_MIDPOINT,
        },
        warnings,
    )
