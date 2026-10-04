from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(l6, l10) -> AnalyzerResult:
    score = (l6.risk_reward + l6.risk_consistency + l10.risk_adjusted_conviction) / 3.0
    return AnalyzerResult("risk_quality", score, min(l6.confidence, l10.confidence))
