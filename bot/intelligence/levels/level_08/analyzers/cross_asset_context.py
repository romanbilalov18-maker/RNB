from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level3_result) -> AnalyzerResult:
    result = next((item for item in level3_result.analyzer_results if item.analyzer == "correlation_context"), None)
    if result is None or result.confidence <= 0:
        return AnalyzerResult("cross_asset_context", 0.0, 0.0, {}, ["cross_asset_history_insufficient"])
    return AnalyzerResult("cross_asset_context", result.score, result.confidence, dict(result.metrics))
