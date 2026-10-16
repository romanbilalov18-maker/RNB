from bot.intelligence.core.models.analysis_result import AnalyzerResult
from ._validation import normalized_value, context_warnings, unavailable


def analyze(level2_result, level4_result) -> AnalyzerResult:
    warnings = context_warnings(None, level2_result, level4_result)
    l2 = normalized_value(level2_result, "score")
    l4 = normalized_value(level4_result, "score")
    c2 = normalized_value(level2_result, "confidence")
    c4 = normalized_value(level4_result, "confidence")
    if warnings or None in (l2, l4, c2, c4):
        return unavailable("signal_confirmation", warnings + ["signal_confirmation_inputs_invalid"])
    agreement = 1.0 - abs(l2 - l4)
    return AnalyzerResult("signal_confirmation", agreement, (c2 + c4) / 2.0, {
        "level2_score": l2, "level4_score": l4,
    })
