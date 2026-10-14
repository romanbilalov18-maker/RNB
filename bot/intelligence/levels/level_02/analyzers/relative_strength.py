from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result


def analyze(snapshot: MarketSnapshot, level1: Level1Result) -> AnalyzerResult:
    results = {
        result.analyzer: result
        for result in level1.analyzer_results
        if result.analyzer in {"momentum", "liquidity"} and result.confidence > 0
    }
    weights = {"momentum": 0.65, "liquidity": 0.35}
    effective = {name: weights[name] * result.confidence for name, result in results.items()}
    total = sum(effective.values())
    if total <= 0:
        return AnalyzerResult("relative_strength", 0.0, 0.0, {"available_inputs": []}, ("relative_strength_inputs_unavailable",))
    score = sum(results[name].score * effective[name] for name in results) / total
    confidence = total / sum(weights[name] for name in results)
    return AnalyzerResult("relative_strength", score, min(1.0, confidence), {"momentum_score": results.get("momentum").score if "momentum" in results else None, "liquidity_score": results.get("liquidity").score if "liquidity" in results else None, "available_inputs": list(results)})
