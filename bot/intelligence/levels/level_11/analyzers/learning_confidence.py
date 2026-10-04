from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(observations, analyzer_results) -> AnalyzerResult:
    if not observations:
        return AnalyzerResult("learning_confidence", 0.0, 0.0, {}, ("learning_history_not_available",))
    base = min(1.0, len(observations) / 20.0)
    quality = sum(item.confidence for item in analyzer_results) / len(analyzer_results) if analyzer_results else 0.0
    return AnalyzerResult("learning_confidence", base * quality, base, {"sample_count": len(observations)})
