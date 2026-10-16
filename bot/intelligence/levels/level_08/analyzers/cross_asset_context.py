import math
from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level3_result) -> AnalyzerResult:
    analyzer_results = getattr(level3_result, "analyzer_results", None)
    if not isinstance(analyzer_results, (list, tuple, dict)):
        return AnalyzerResult("cross_asset_context", 0.0, 0.0, {}, ("cross_asset_history_insufficient",))
    values = analyzer_results.values() if isinstance(analyzer_results, dict) else analyzer_results
    result = next((item for item in values if getattr(item, "analyzer", None) == "correlation_context"), None)
    score = getattr(result, "score", None)
    confidence = getattr(result, "confidence", None)
    if (result is None or isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score)
            or not 0.0 <= score <= 1.0 or isinstance(confidence, bool) or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence) or not 0.0 < confidence <= 1.0):
        return AnalyzerResult("cross_asset_context", 0.0, 0.0, {}, ("cross_asset_history_insufficient",))
    return AnalyzerResult("cross_asset_context", score, confidence, dict(getattr(result, "metrics", {}) or {}))
