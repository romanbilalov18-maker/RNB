from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level3_result) -> AnalyzerResult:
    directional = min(1.0, abs(snapshot.momentum) * 10.0)
    score = min(1.0, directional * 0.65 + level3_result.consistency * 0.35)
    return AnalyzerResult("trend_persistence", score, level3_result.confidence, {"directional_strength": directional, "market_consistency": level3_result.consistency})
