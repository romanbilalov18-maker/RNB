from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level3_result) -> AnalyzerResult:
    score = max(0.0, min(1.0, 0.5 + snapshot.momentum * 6.0))
    return AnalyzerResult("market_relative_strength", score, level3_result.confidence, {"momentum_proxy": snapshot.momentum}, ["market_benchmark_not_available"])
