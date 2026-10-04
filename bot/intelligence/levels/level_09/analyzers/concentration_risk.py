from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level6_result) -> AnalyzerResult:
    risk = max(level6_result.downside_risk, level6_result.volatility_risk)
    score = min(1.0, max(0.0, risk))
    return AnalyzerResult("concentration_risk", score, level6_result.confidence, {"risk_proxy": risk}, ["portfolio_positions_not_available"])
