from bot.intelligence.core.models.analysis_result import AnalyzerResult
from ._validation import normalized_value, context_warnings, unavailable


def analyze(level2_result, level3_result, level4_result) -> AnalyzerResult:
    warnings = context_warnings(None, level2_result, level3_result, level4_result)
    values = [normalized_value(item, "score") for item in (level2_result, level3_result, level4_result)]
    confidences = [normalized_value(item, "confidence") for item in (level2_result, level3_result, level4_result)]
    if warnings or any(value is None for value in values + confidences):
        return unavailable("signal_consistency", warnings + ["signal_consistency_inputs_invalid"])
    spread = max(values) - min(values)
    confidence = sum(confidences) / len(confidences)
    return AnalyzerResult("signal_consistency", 1.0 - spread, confidence, {"spread": spread})
