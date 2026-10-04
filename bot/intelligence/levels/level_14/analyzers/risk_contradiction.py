from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level6_result, level10_result) -> AnalyzerResult:
    risk = level6_result.downside_risk
    reward = level6_result.reward_potential
    conviction = level10_result.risk_adjusted_conviction
    score = min(1.0, 0.50 * risk + 0.30 * max(0.0, risk - reward) + 0.20 * conviction * risk)
    return AnalyzerResult("risk_contradiction", score, min(level6_result.confidence, level10_result.confidence))
