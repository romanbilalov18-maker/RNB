from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(l11) -> AnalyzerResult:
    sample_count = getattr(l11, "sample_count", None)
    confidence = getattr(l11, "confidence", 0.0)
    # Current L11 results expose sample_count; older/test-compatible result
    # objects may not, so only use confidence to judge those legacy objects.
    unavailable = (
        (sample_count is not None and (
            not isinstance(sample_count, int)
            or isinstance(sample_count, bool)
            or sample_count <= 0
        ))
        or (sample_count is None and confidence <= 0.0)
    )
    if unavailable:
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
        {"sample_count": sample_count},
    )
