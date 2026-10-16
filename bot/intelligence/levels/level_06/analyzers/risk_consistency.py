from bot.intelligence.core.models.analysis_result import AnalyzerResult
from ._validation import number, result_or_unavailable


def analyze(level5_result, downside_result, risk_reward_result) -> AnalyzerResult:
    if any(item is None for item in (level5_result, downside_result, risk_reward_result)):
        return result_or_unavailable("risk_consistency", ["risk_consistency_inputs_not_available"])
    l5 = number(getattr(level5_result, "score", None), minimum=0.0, maximum=1.0)
    l5_conf = number(getattr(level5_result, "confidence", None), minimum=0.0, maximum=1.0)
    downside = number(getattr(downside_result, "score", None), minimum=0.0, maximum=1.0)
    downside_conf = number(getattr(downside_result, "confidence", None), minimum=0.0, maximum=1.0)
    rr = number(getattr(risk_reward_result, "score", None), minimum=0.0, maximum=1.0)
    rr_conf = number(getattr(risk_reward_result, "confidence", None), minimum=0.0, maximum=1.0)
    if None in (l5, l5_conf, downside, downside_conf, rr, rr_conf):
        return result_or_unavailable("risk_consistency", ["risk_consistency_inputs_invalid"])
    values = [downside, 1.0 - rr, 1.0 - l5]
    spread = max(values) - min(values)
    score = 1.0 - spread
    output_confidence = min(l5_conf, downside_conf, rr_conf)
    warnings = () if output_confidence > 0 else ("risk_consistency_evidence_unavailable",)
    return AnalyzerResult("risk_consistency", score, output_confidence, {"spread": spread}, warnings)
