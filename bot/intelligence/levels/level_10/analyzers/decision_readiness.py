from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(conviction, agreement, confidence_quality, risk_adjusted, warning_impact):
    score = (conviction.score * 0.25 + agreement.score * 0.25 + confidence_quality.score * 0.20 + risk_adjusted.score * 0.20 + warning_impact.score * 0.10)
    confidence = min(conviction.confidence, agreement.confidence, confidence_quality.confidence, risk_adjusted.confidence, warning_impact.confidence)
    return AnalyzerResult("decision_readiness", score, confidence, {})
