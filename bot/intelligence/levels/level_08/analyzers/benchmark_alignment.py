from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level7_result) -> AnalyzerResult:
    score = max(0.0, min(1.0, 0.5 + snapshot.price_change() * 6.0))
    return AnalyzerResult("benchmark_alignment", score, 0.25, {}, ["benchmark_data_not_available"])
