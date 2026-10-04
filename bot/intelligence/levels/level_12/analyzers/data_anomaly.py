from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot) -> AnalyzerResult:
    missing = sum(
        value is None
        for value in (
            snapshot.previous_price,
            snapshot.volume,
            snapshot.average_volume,
            snapshot.volatility,
            snapshot.momentum,
            snapshot.liquidity,
        )
    )
    score = min(1.0, missing / 6.0)
    confidence = 1.0 - score
    warnings = ("market_snapshot_incomplete",) if missing else ()
    return AnalyzerResult("data_anomaly", score, confidence, {"missing_fields": missing}, warnings)
