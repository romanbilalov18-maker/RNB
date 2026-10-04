from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot) -> AnalyzerResult:
    change = snapshot.price_change()
    if change is None:
        return AnalyzerResult("price_anomaly", 0.0, 0.0, {}, ("previous_price_not_available",))
    score = min(1.0, abs(change) / 0.10)
    return AnalyzerResult("price_anomaly", score, 0.9, {"price_change": change})
