from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(l13) -> AnalyzerResult:
    score = (l13.scenario_confidence + l13.neutral_scenario + (1.0 - l13.adverse_scenario)) / 3.0
    return AnalyzerResult("scenario_quality", score, l13.confidence)
