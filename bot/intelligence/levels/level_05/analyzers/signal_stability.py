from bot.intelligence.core.models.analysis_result import AnalyzerResult
from ._validation import normalized_value, context_warnings, unavailable


def analyze(level3_result, level4_result) -> AnalyzerResult:
    warnings = context_warnings(None, level3_result, level4_result)
    s3 = normalized_value(level3_result, "consistency")
    s4 = normalized_value(level4_result, "consistency")
    c3 = normalized_value(level3_result, "confidence")
    c4 = normalized_value(level4_result, "confidence")
    if warnings or None in (s3, s4, c3, c4):
        return unavailable("signal_stability", warnings + ["signal_stability_inputs_invalid"])
    return AnalyzerResult("signal_stability", (s3 + s4) / 2.0, (c3 + c4) / 2.0, {
        "level3_consistency": s3, "level4_consistency": s4,
    })
