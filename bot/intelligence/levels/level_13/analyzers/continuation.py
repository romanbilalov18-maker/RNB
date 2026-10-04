from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level7_result, level10_result) -> AnalyzerResult:
    momentum = abs(snapshot.momentum or 0.0)
    persistence = level7_result.trend_persistence
    conviction = level10_result.conviction
    score = min(1.0, 0.35 * min(1.0, momentum / 0.10) + 0.35 * persistence + 0.30 * conviction)
    return AnalyzerResult("continuation", score, min(level7_result.confidence, level10_result.confidence))
