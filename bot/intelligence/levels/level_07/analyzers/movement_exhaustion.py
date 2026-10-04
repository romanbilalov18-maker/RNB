from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level6_result) -> AnalyzerResult:
    extension = min(1.0, abs(snapshot.momentum) * 8.0)
    volatility = min(1.0, max(0.0, snapshot.volatility) * 12.0)
    score = min(1.0, extension * 0.65 + volatility * 0.35)
    return AnalyzerResult("movement_exhaustion", score, level6_result.confidence, {"extension": extension, "volatility": volatility})
