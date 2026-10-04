from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level6_result, level7_result) -> AnalyzerResult:
    volatility = min(1.0, max(0.0, (snapshot.volatility or 0.0) / 0.10))
    acceleration = level7_result.momentum_acceleration
    risk = level6_result.volatility_risk
    score = min(1.0, 0.45 * volatility + 0.30 * acceleration + 0.25 * risk)
    return AnalyzerResult("volatility_expansion", score, min(level6_result.confidence, level7_result.confidence))
