from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level5_result, downside_result, risk_reward_result) -> AnalyzerResult:
    # High score means the risk conclusion is internally coherent, not that risk is low.
    values = [downside_result.score, 1.0 - risk_reward_result.score, 1.0 - level5_result.score]
    spread = max(values) - min(values)
    score = max(0.0, min(1.0, 1.0 - spread))
    confidence = min(
        max(0.0, min(1.0, float(level5_result.confidence))),
        max(0.0, min(1.0, float(downside_result.confidence))),
        max(0.0, min(1.0, float(risk_reward_result.confidence))),
    )
    warnings = () if confidence > 0 else ("risk_consistency_evidence_unavailable",)
    return AnalyzerResult("risk_consistency", score, confidence, {"spread": spread}, warnings)
