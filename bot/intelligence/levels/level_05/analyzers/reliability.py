from bot.intelligence.core.models.analysis_result import AnalyzerResult
from ._validation import normalized_value, context_warnings, unavailable


def analyze(level3_result, level4_result) -> AnalyzerResult:
    warnings = context_warnings(None, level3_result, level4_result)
    c3 = normalized_value(level3_result, "confidence")
    c4 = normalized_value(level4_result, "confidence")
    if warnings or None in (c3, c4):
        return unavailable("reliability", warnings + ["reliability_inputs_invalid"])
    source_warnings = set(getattr(level3_result, "warnings", ()) or ()) | set(getattr(level4_result, "warnings", ()) or ())
    warning_penalty = min(0.35, 0.05 * len(source_warnings))
    score = max(0.0, (c3 + c4) / 2.0 - warning_penalty)
    return AnalyzerResult("reliability", score, (c3 + c4) / 2.0, {
        "warning_penalty": warning_penalty, "source_warning_count": len(source_warnings),
    })
