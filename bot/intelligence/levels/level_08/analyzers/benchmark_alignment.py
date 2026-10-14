from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level7_result) -> AnalyzerResult:
    if snapshot.relative_market_context_available:
        market_return = snapshot.relative_market_return
        sample_count = snapshot.relative_market_sample_count
    else:
        market_return = snapshot.market_return
        sample_count = snapshot.market_sample_count
    if market_return is None or sample_count < 10:
        return AnalyzerResult("benchmark_alignment", 0.0, 0.0, {"sample_count": sample_count}, ["market_benchmark_not_available"])
    change = snapshot.price_change()
    if change is None:
        return AnalyzerResult("benchmark_alignment", 0.0, 0.0, {}, ["asset_return_not_available"])
    relative = change - market_return
    score = max(0.0, min(1.0, 0.5 + relative * 8.0))
    return AnalyzerResult("benchmark_alignment", score, min(1.0, sample_count / 100.0), {"asset_return": change, "market_return": market_return, "relative_return": relative, "sample_count": sample_count, "benchmark": "leave_one_out_tradable_RUB_share_universe"})
