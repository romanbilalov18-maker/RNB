from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level5_result) -> AnalyzerResult:
    volatility = max(0.0, snapshot.volatility)
    momentum_risk = max(0.0, -snapshot.momentum)
    score = min(1.0, volatility * 12.0 * 0.65 + momentum_risk * 5.0 * 0.35)
    return AnalyzerResult("downside_risk", score, level5_result.confidence, {"volatility": volatility, "negative_momentum": momentum_risk})
