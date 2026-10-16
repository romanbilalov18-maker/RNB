from bot.intelligence.core.models.analysis_result import AnalyzerResult
from ._validation import number, result_or_unavailable


def analyze(downside_result, reward_result) -> AnalyzerResult:
    if downside_result is None or reward_result is None:
        return result_or_unavailable("risk_reward", ["risk_reward_inputs_not_available"])
    risk = number(getattr(downside_result, "score", None), minimum=0.0, maximum=1.0)
    reward = number(getattr(reward_result, "score", None), minimum=0.0, maximum=1.0)
    risk_conf = number(getattr(downside_result, "confidence", None), minimum=0.0, maximum=1.0)
    reward_conf = number(getattr(reward_result, "confidence", None), minimum=0.0, maximum=1.0)
    if None in (risk, reward, risk_conf, reward_conf):
        return result_or_unavailable("risk_reward", ["risk_reward_inputs_invalid"])
    if risk == 0.0 and reward == 0.0:
        return result_or_unavailable("risk_reward", ["risk_reward_both_components_zero"])
    score = reward / (reward + risk)
    return AnalyzerResult("risk_reward", score, min(risk_conf, reward_conf), {"risk": risk, "reward": reward})
