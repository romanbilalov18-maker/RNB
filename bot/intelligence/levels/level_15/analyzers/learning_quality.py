from bot.intelligence.core.models.analysis_result import AnalyzerResult

# L11 uses per-ticker outcomes. A handful of observations is not enough
# evidence to influence the final trading gate. Keep it diagnostic until the
# same minimum sample size used by the learning/Bayesian analyzers is reached.
MIN_LEARNING_SAMPLES = 20

_COMPONENTS = (
    "outcome_quality",
    "level_effectiveness",
    "analyzer_effectiveness",
    "learning_confidence",
)


def analyze(l11) -> AnalyzerResult:
    sample_count = getattr(l11, "sample_count", None)
    confidence = getattr(l11, "confidence", 0.0)

    # Compatibility for older/test-shaped result objects without sample_count.
    if sample_count is None:
        if confidence <= 0.0:
            return AnalyzerResult(
                "learning_quality", 0.0, 0.0, {"sample_count": 0},
                ("learning_evidence_unavailable",),
            )
        score = (
            l11.outcome_quality + l11.level_effectiveness
            + l11.analyzer_effectiveness + l11.learning_confidence
        ) / 4.0
        return AnalyzerResult(
            "learning_quality", max(0.0, min(1.0, score)),
            max(0.0, min(1.0, confidence)),
            {"sample_count": None, "legacy_result_compatibility": True},
        )

    if (
        isinstance(sample_count, bool)
        or not isinstance(sample_count, int)
        or sample_count < MIN_LEARNING_SAMPLES
    ):
        return AnalyzerResult(
            "learning_quality", 0.0, 0.0,
            {
                "sample_count": sample_count if isinstance(sample_count, int) else None,
                "minimum_required_samples": MIN_LEARNING_SAMPLES,
                "learning_applied_to_decision": False,
            },
            ("learning_evidence_below_minimum_samples",),
        )

    results = getattr(l11, "analyzer_results", ()) or ()
    by_name = {
        getattr(result, "analyzer", None): result
        for result in results
        if getattr(result, "analyzer", None) in _COMPONENTS
    }
    available = [
        (name, by_name[name])
        for name in _COMPONENTS
        if name in by_name and getattr(by_name[name], "confidence", 0.0) > 0.0
    ]
    total_confidence = sum(float(result.confidence) for _, result in available)
    if total_confidence <= 0.0:
        return AnalyzerResult(
            "learning_quality", 0.0, 0.0,
            {
                "sample_count": sample_count,
                "minimum_required_samples": MIN_LEARNING_SAMPLES,
                "available_components": [],
                "learning_applied_to_decision": False,
            },
            ("learning_component_evidence_unavailable",),
        )

    # Do not average unavailable components' default score=0 into the result.
    # Weight each available component by its own evidence confidence.
    score = sum(
        float(result.score) * float(result.confidence)
        for _, result in available
    ) / total_confidence
    return AnalyzerResult(
        "learning_quality",
        max(0.0, min(1.0, score)),
        max(0.0, min(1.0, float(confidence))),
        {
            "sample_count": sample_count,
            "minimum_required_samples": MIN_LEARNING_SAMPLES,
            "available_components": [name for name, _ in available],
            "excluded_components": [name for name in _COMPONENTS if name not in {n for n, _ in available}],
            "component_confidence_weighted": True,
            "learning_applied_to_decision": True,
        },
    )
