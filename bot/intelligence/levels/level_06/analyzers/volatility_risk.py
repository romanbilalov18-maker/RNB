from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot) -> AnalyzerResult:
    volatility = getattr(snapshot, "volatility", None)
    if volatility is None:
        return AnalyzerResult(
            "volatility_risk", 0.0, 0.0, {},
            ("volatility_data_not_available",),
        )
    volatility = max(0.0, float(volatility))
    score = min(1.0, volatility * 12.0)
    return AnalyzerResult("volatility_risk", score, 0.85, {"volatility": volatility})
