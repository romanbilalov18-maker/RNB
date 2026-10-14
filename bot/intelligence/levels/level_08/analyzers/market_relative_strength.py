from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level3_result) -> AnalyzerResult:
    if snapshot.relative_market_context_available:
        market_return = snapshot.relative_market_return
        sample_count = snapshot.relative_market_sample_count
    else:
        market_return = snapshot.market_return
        sample_count = snapshot.market_sample_count
    if market_return is None or sample_count < 10:
        return AnalyzerResult("market_relative_strength", 0.0, 0.0, {"sample_count": sample_count}, ["market_benchmark_not_available"])
    change = snapshot.price_change()
    relative = (change - market_return) if change is not None else None
    if relative is None:
        return AnalyzerResult("market_relative_strength", 0.0, 0.0, {"market_return": market_return}, ["asset_return_not_available"])
    score = max(0.0, min(1.0, 0.5 + relative * 8.0))
    confidence = min(1.0, sample_count / 100.0)
    return AnalyzerResult("market_relative_strength", score, confidence, {"asset_return": change, "market_return": market_return, "relative_return": relative, "sample_count": sample_count, "benchmark": "leave_one_out_tradable_RUB_share_universe"})
