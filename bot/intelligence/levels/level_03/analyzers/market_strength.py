from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


def analyze(snapshot: MarketSnapshot, level2: Level2Result) -> AnalyzerResult:
    results = {
        result.analyzer: result
        for result in level2.analyzer_results
        if result.analyzer in {"relative_strength", "volume_flow"} and result.confidence > 0
    }
    weights = {"relative_strength": 0.60, "volume_flow": 0.40}
    effective = {name: weights[name] * result.confidence for name, result in results.items()}
    total = sum(effective.values())
    if total <= 0:
        return AnalyzerResult("market_strength", 0.0, 0.0, {"available_inputs": []}, ("market_strength_inputs_unavailable",))
    score = sum(results[name].score * effective[name] for name in results) / total
    confidence = total / sum(weights[name] for name in results)
    return AnalyzerResult("market_strength", score, min(1.0, confidence), {"relative_strength": results.get("relative_strength").score if "relative_strength" in results else None, "volume_flow": results.get("volume_flow").score if "volume_flow" in results else None, "available_inputs": list(results)})
