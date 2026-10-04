from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level5_result, level8_result) -> AnalyzerResult:
    score = min(1.0, max(0.0, 0.5 * level5_result.score + 0.5 * level8_result.score))
    return AnalyzerResult("portfolio_compatibility", score, min(level5_result.confidence, level8_result.confidence), {}, ["existing_positions_not_available"])
