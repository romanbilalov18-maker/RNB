from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(observations, analyzer_results) -> AnalyzerResult:
    if not observations:
        return AnalyzerResult("learning_confidence", 0.0, 0.0, {}, ("learning_history_not_available",))
    base = min(1.0, len(observations) / 20.0)
    # Unavailable analyzers carry confidence=0; do not count them as evidence
    # of poor learning quality when estimating confidence in the available set.
    available = [
        item for item in (analyzer_results or ())
        if getattr(item, "confidence", 0.0) > 0.0
    ]
    quality = (
        sum(item.confidence for item in available) / len(available)
        if available else 0.0
    )
    return AnalyzerResult(
        "learning_confidence",
        base * quality,
        base if available else 0.0,
        {
            "sample_count": len(observations),
            "available_analyzer_count": len(available),
            "unavailable_analyzers_excluded": True,
        },
    )
