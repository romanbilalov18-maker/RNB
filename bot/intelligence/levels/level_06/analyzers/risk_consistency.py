from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level5_result, downside_result, risk_reward_result) -> AnalyzerResult:
    # High score means the risk conclusion is internally coherent, not that risk is low.
    values = [downside_result.score, 1.0 - risk_reward_result.score, 1.0 - level5_result.score]
    spread = max(values) - min(values)
    score = max(0.0, min(1.0, 1.0 - spread))
    return AnalyzerResult("risk_consistency", score, level5_result.confidence, {"spread": spread})
