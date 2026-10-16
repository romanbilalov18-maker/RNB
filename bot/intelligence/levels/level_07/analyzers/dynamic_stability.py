from bot.intelligence.core.models.analysis_result import AnalyzerResult
from ._validation import metric, unavailable


def analyze(level5_result, level6_result) -> AnalyzerResult:
    if level5_result is None or level6_result is None:
        return unavailable("dynamic_stability", ["stability_context_not_available"])
    stability = metric(level5_result, "signal_stability")
    risk_consistency = metric(level6_result, "consistency")
    c5 = metric(level5_result, "confidence")
    c6 = metric(level6_result, "confidence")
    if None in (stability, risk_consistency, c5, c6):
        return unavailable("dynamic_stability", ["dynamic_stability_inputs_invalid"])
    score = (stability + risk_consistency) / 2.0
    return AnalyzerResult("dynamic_stability", score, min(c5, c6), {"signal_stability": stability, "risk_consistency": risk_consistency})
