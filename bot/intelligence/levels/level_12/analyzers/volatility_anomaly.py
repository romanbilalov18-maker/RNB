from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot) -> AnalyzerResult:
    if snapshot.volatility is None:
        return AnalyzerResult("volatility_anomaly", 0.0, 0.0, {}, ("volatility_not_available",))
    score = min(1.0, max(0.0, snapshot.volatility / 0.10))
    return AnalyzerResult("volatility_anomaly", score, 0.85, {"volatility": snapshot.volatility})
