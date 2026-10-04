from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level6_result, level10_result, level12_result) -> AnalyzerResult:
    risk = level6_result.downside_risk
    adverse = level6_result.adverse_scenario
    anomaly = level12_result.score
    warning_factor = min(1.0, len(level12_result.warnings) / 5.0)
    score = min(1.0, 0.40 * risk + 0.35 * adverse + 0.15 * anomaly + 0.10 * warning_factor)
    return AnalyzerResult("adverse_scenario", score, min(level6_result.confidence, level10_result.confidence))
