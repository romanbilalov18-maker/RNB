from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level3_result) -> AnalyzerResult:
    score = max(0.0, min(1.0, level3_result.correlation_context if hasattr(level3_result, "correlation_context") else level3_result.consistency))
    return AnalyzerResult("cross_asset_context", score, 0.25, {}, ["cross_asset_data_not_available"])
