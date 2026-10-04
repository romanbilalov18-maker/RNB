from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(results) -> AnalyzerResult:
    if not results:
        return AnalyzerResult("scenario_confidence", 0.0, 0.0, {}, ("scenario_results_not_available",))
    scores = [result.score for result in results]
    spread = max(scores) - min(scores)
    confidence = max(result.confidence for result in results)
    score = max(0.0, min(1.0, 1.0 - spread))
    return AnalyzerResult("scenario_confidence", score, confidence, {"scenario_spread": spread})
