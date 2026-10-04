from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(observations) -> AnalyzerResult:
    if not observations:
        return AnalyzerResult("analyzer_effectiveness", 0.5, 0.0, {}, ("learning_history_not_available",))
    names = sorted({name for item in observations for name in item.analyzer_scores})
    if not names:
        return AnalyzerResult("analyzer_effectiveness", 0.5, 0.0, {}, ("analyzer_history_not_available",))
    values = [sum(item.analyzer_scores.get(name, 0.5) for item in observations) / len(observations) for name in names]
    return AnalyzerResult("analyzer_effectiveness", sum(values) / len(values), min(1.0, len(observations) / 20.0), {"analyzers": names})
