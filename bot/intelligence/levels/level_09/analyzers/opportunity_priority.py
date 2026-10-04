from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level5_result, level6_result, level8_result) -> AnalyzerResult:
    score = min(1.0, max(0.0, level5_result.score * 0.35 + level6_result.risk_reward * 0.35 + level8_result.score * 0.30))
    return AnalyzerResult("opportunity_priority", score, min(level5_result.confidence, level6_result.confidence, level8_result.confidence), {})
