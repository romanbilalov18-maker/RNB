from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level3_result) -> AnalyzerResult:
    score = max(0.0, min(1.0, level3_result.relative_market if hasattr(level3_result, "relative_market") else level3_result.score))
    return AnalyzerResult("sector_relative_strength", score, 0.35, {}, ["sector_data_not_available"])
