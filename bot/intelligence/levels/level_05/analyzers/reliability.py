from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level3_result, level4_result) -> AnalyzerResult:
    warning_penalty = min(0.35, 0.05 * len(set(level3_result.warnings + level4_result.warnings)))
    score = max(0.0, min(1.0, 0.5 * level3_result.confidence + 0.5 * level4_result.confidence - warning_penalty))
    confidence = max(0.0, min(1.0, (level3_result.confidence + level4_result.confidence) / 2.0))
    return AnalyzerResult("reliability", score, confidence, {"warning_penalty": warning_penalty})
