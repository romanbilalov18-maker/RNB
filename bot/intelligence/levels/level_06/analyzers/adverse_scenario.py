from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level5_result) -> AnalyzerResult:
    pressure = max(0.0, 0.5 - getattr(level5_result, "signal_confirmation", 0.5))
    volatility = min(1.0, max(0.0, snapshot.volatility * 12.0))
    score = min(1.0, pressure * 0.55 + volatility * 0.45)
    return AnalyzerResult("adverse_scenario", score, level5_result.confidence, {"pressure_risk": pressure, "volatility": volatility})
