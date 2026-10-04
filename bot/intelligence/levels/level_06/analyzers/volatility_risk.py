from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot) -> AnalyzerResult:
    volatility = max(0.0, snapshot.volatility)
    score = min(1.0, volatility * 12.0)
    return AnalyzerResult("volatility_risk", score, 0.85, {"volatility": volatility})
