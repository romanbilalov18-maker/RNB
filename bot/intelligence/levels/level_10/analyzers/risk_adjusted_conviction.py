from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level5, level6, level9):
    score = max(0.0, min(1.0, level5.score * 0.4 + level6.risk_reward * 0.35 + level9.opportunity_priority * 0.25))
    return AnalyzerResult("risk_adjusted_conviction", score, min(level5.confidence, level6.confidence, level9.confidence), {})
