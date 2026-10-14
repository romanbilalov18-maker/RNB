from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


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
        return AnalyzerResult("market_regime", 0.0, 0.0, {"available_inputs": []}, ("market_regime_inputs_unavailable",))
    score = sum(results[name].score * effective[name] for name in results) / total
    confidence = sum(effective.values()) / sum(weights[name] for name in results)
    return AnalyzerResult("market_regime", score, min(1.0, confidence), {"trend_score": results.get("trend").score if "trend" in results else None, "structure_score": results.get("price_structure").score if "price_structure" in results else None, "available_inputs": list(results)})
