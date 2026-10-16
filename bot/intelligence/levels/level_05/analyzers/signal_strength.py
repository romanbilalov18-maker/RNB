from bot.intelligence.core.models.analysis_result import AnalyzerResult
from ._validation import normalized_value, context_warnings, unavailable


def analyze(level3_result, level4_result) -> AnalyzerResult:
    warnings = context_warnings(None, level3_result, level4_result)
    l3 = normalized_value(level3_result, "score")
    l4 = normalized_value(level4_result, "score")
    c3 = normalized_value(level3_result, "confidence")
    c4 = normalized_value(level4_result, "confidence")
    if warnings or None in (l3, l4, c3, c4):
        return unavailable("signal_strength", warnings + ["signal_strength_inputs_invalid"])
    confidence = (c3 + c4) / 2.0
    score = l3 * 0.55 + l4 * 0.45
    return AnalyzerResult("signal_strength", score, confidence, {
        "level3_score": l3, "level4_score": l4,
    })
