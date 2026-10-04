from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level8_result, level6_result) -> AnalyzerResult:
    risk = max(0.0, 1.0 - level8_result.cross_asset_context) if level8_result.cross_asset_context >= 0 else 1.0
    score = min(1.0, max(0.0, risk * 0.7 + level6_result.adverse_scenario * 0.3))
    return AnalyzerResult("correlation_risk", score, min(level8_result.confidence, level6_result.confidence), {}, level8_result.warnings)
