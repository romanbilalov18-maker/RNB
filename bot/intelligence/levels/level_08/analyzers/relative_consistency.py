import math
from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level3_result, level7_result) -> AnalyzerResult:
    if level3_result is None or level7_result is None:
        return AnalyzerResult("relative_consistency", 0.0, 0.0, {}, ("relative_context_not_available",))
    score3, score7 = getattr(level3_result, "score", None), getattr(level7_result, "score", None)
    conf3, conf7 = getattr(level3_result, "confidence", None), getattr(level7_result, "confidence", None)
    values = (score3, score7, conf3, conf7)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0.0 <= v <= 1.0 for v in values):
        return AnalyzerResult("relative_consistency", 0.0, 0.0, {}, ("relative_context_inputs_invalid",))
    score = max(0.0, min(1.0, 1.0 - abs(score3 - score7)))
    confidence = min(conf3, conf7)
    return AnalyzerResult("relative_consistency", score, confidence, {"level3_score": score3, "level7_score": score7})
