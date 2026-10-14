from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level7_result) -> AnalyzerResult:
    if snapshot.market_return is None or snapshot.market_sample_count < 10:
        return AnalyzerResult("benchmark_alignment", 0.0, 0.0, {}, ["market_benchmark_not_available"])
    change = snapshot.price_change()
    if change is None:
        return AnalyzerResult("benchmark_alignment", 0.0, 0.0, {}, ["asset_return_not_available"])
    relative = change - snapshot.market_return
    score = max(0.0, min(1.0, 0.5 + relative * 8.0))
    return AnalyzerResult("benchmark_alignment", score, min(1.0, snapshot.market_sample_count / 100.0), {"asset_return": change, "market_return": snapshot.market_return, "relative_return": relative, "benchmark": "tradable_RUB_share_universe"})
