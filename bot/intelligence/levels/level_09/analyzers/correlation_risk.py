from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level8_result, level6_result) -> AnalyzerResult:
    cross = next((item for item in level8_result.analyzer_results.values() if item.analyzer == "cross_asset_context"), None)
    correlation = cross.metadata.get("pearson_correlation") if cross is not None else None
    if correlation is None or cross.confidence <= 0:
        return AnalyzerResult("correlation_risk", 0.0, 0.0, {}, ["cross_asset_correlation_not_available"])
    risk = max(0.0, min(1.0, abs(float(correlation))))
    score = max(0.0, min(1.0, 0.7 * risk + 0.3 * level6_result.adverse_scenario))
    return AnalyzerResult("correlation_risk", score, min(cross.confidence, level6_result.confidence), {"pearson_correlation": correlation, "absolute_correlation_risk": risk})
