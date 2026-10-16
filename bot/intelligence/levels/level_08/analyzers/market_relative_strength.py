import math
from bot.intelligence.core.models.analysis_result import AnalyzerResult


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def analyze(snapshot, level3_result) -> AnalyzerResult:
    if getattr(snapshot, "relative_market_context_available", False):
        market_return = getattr(snapshot, "relative_market_return", None)
        sample_count = getattr(snapshot, "relative_market_sample_count", None)
    else:
        market_return = getattr(snapshot, "market_return", None)
        sample_count = getattr(snapshot, "market_sample_count", None)
    if not _finite(market_return) or not isinstance(sample_count, int) or isinstance(sample_count, bool) or sample_count < 10:
        return AnalyzerResult("market_relative_strength", 0.0, 0.0, {"sample_count": sample_count}, ("market_benchmark_not_available",))
    change = snapshot.price_change()
    if not _finite(change):
        return AnalyzerResult("market_relative_strength", 0.0, 0.0, {"market_return": market_return}, ("asset_return_not_available",))
    relative = change - market_return
    score = max(0.0, min(1.0, 0.5 + relative * 8.0))
    confidence = min(1.0, sample_count / 100.0)
    return AnalyzerResult("market_relative_strength", score, confidence, {"asset_return": change, "market_return": market_return, "relative_return": relative, "sample_count": sample_count, "benchmark": "leave_one_out_tradable_RUB_share_universe"})
