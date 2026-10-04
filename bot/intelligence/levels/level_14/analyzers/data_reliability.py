from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level10_result, level12_result, level13_result) -> AnalyzerResult:
    warning_count = len(set(level10_result.warnings + list(level12_result.warnings) + list(level13_result.warnings)))
    score = max(0.0, min(1.0, 1.0 - warning_count / 10.0))
    confidence = score
    warnings = ("adversarial_data_warnings_present",) if warning_count else ()
    return AnalyzerResult("data_reliability", score, confidence, {"warning_count": warning_count}, warnings)
