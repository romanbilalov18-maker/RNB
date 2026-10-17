from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level6_result, level10_result, level12_result) -> AnalyzerResult:
    risk = level6_result.downside_risk
    adverse = level6_result.adverse_scenario
    anomaly = level12_result.score
    warning_factor = min(1.0, len(level12_result.warnings) / 5.0)
    score = min(1.0, 0.40 * risk + 0.35 * adverse + 0.15 * anomaly + 0.10 * warning_factor)
    # Confidence must reflect every level used to construct this scenario.
    # If L12 cannot support its anomaly assessment, the adverse forecast
    # must not appear highly reliable just because L6 and L10 are confident.
    confidence = min(
        level6_result.confidence,
        level10_result.confidence,
        level12_result.confidence,
    )
    return AnalyzerResult("adverse_scenario", score, confidence)
