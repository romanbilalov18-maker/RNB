from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level3_result) -> AnalyzerResult:
    if snapshot.market_return is None or snapshot.market_sample_count < 10:
        return AnalyzerResult("market_relative_strength", 0.0, 0.0, {}, ["market_benchmark_not_available"])
    change = snapshot.price_change()
    relative = (change - snapshot.market_return) if change is not None else None
    if relative is None:
        return AnalyzerResult("market_relative_strength", 0.0, 0.0, {"market_return": snapshot.market_return}, ["asset_return_not_available"])
    score = max(0.0, min(1.0, 0.5 + relative * 8.0))
    confidence = min(1.0, snapshot.market_sample_count / 100.0)
    return AnalyzerResult("market_relative_strength", score, confidence, {"asset_return": change, "market_return": snapshot.market_return, "relative_return": relative, "sample_count": snapshot.market_sample_count})
