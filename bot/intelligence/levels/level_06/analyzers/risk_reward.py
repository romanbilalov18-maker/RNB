from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(downside_result, reward_result) -> AnalyzerResult:
    reward = reward_result.score
    risk = downside_result.score
    score = reward / (reward + risk + 1e-9)
    return AnalyzerResult("risk_reward", score, min(downside_result.confidence, reward_result.confidence), {"risk": risk, "reward": reward})
