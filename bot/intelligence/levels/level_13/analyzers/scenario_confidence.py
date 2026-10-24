from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(results) -> AnalyzerResult:
    if not results:
        return AnalyzerResult("scenario_confidence", 0.0, 0.0, {}, ("scenario_results_not_available",))
    if not any(result.confidence > 0 for result in results):
        return AnalyzerResult("scenario_confidence", 0.0, 0.0, {"available": False}, ("scenario_confidence_unavailable",))
    # Confidence zero marks a forecast as unavailable; exclude it from agreement.
    available = [result for result in results if result.confidence > 0.0]
    scores = [result.score for result in available]
    spread = max(scores) - min(scores)
    confidence = max(result.confidence for result in available)
    score = max(0.0, min(1.0, 1.0 - spread))
    return AnalyzerResult("scenario_confidence", score, confidence, {"scenario_spread": spread})
