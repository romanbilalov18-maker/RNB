from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level10_result, level12_result, level13_result) -> AnalyzerResult:
    warning_sources = (
        tuple(level10_result.warnings or ()),
        tuple(level12_result.warnings or ()),
        tuple(level13_result.warnings or ()),
    )
    warning_count = len(set(warning for source in warning_sources for warning in source))

    # L12 explicitly measures data anomalies; warnings add a separate penalty.
    anomaly = max(0.0, min(1.0, float(level12_result.data_anomaly)))
    warning_penalty = min(1.0, warning_count / 10.0)
    score = max(0.0, min(1.0, (1.0 - anomaly) * (1.0 - warning_penalty)))

    # Reliability is only as trustworthy as the sources it summarizes.
    confidence = min(
        max(0.0, min(1.0, float(level10_result.confidence))),
        max(0.0, min(1.0, float(level12_result.confidence))),
        max(0.0, min(1.0, float(level13_result.confidence))),
    )
    warnings = ("adversarial_data_warnings_present",) if warning_count else ()
    return AnalyzerResult(
        "data_reliability",
        score,
        confidence,
        {"data_anomaly": anomaly, "warning_count": warning_count, "warning_penalty": warning_penalty},
        warnings,
    )
