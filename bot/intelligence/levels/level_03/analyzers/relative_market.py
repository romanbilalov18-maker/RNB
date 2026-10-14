from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


def analyze(snapshot: MarketSnapshot, level2: Level2Result) -> AnalyzerResult:
    results = {
        result.analyzer: result
        for result in level2.analyzer_results
        if result.analyzer in {"relative_strength", "trend"} and result.confidence > 0
    }
    weights = {"relative_strength": 0.55, "trend": 0.45}
    effective = {name: weights[name] * result.confidence for name, result in results.items()}
    total = sum(effective.values())
    if total <= 0:
        return AnalyzerResult("relative_market", 0.0, 0.0, {"available_inputs": []}, ("relative_market_inputs_unavailable",))
    score = sum(results[name].score * effective[name] for name in results) / total
    confidence = total / sum(weights[name] for name in results)
    return AnalyzerResult("relative_market", score, min(1.0, confidence), {"strength": results.get("relative_strength").score if "relative_strength" in results else None, "trend": results.get("trend").score if "trend" in results else None, "available_inputs": list(results)})
