from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(observations) -> AnalyzerResult:
    if not observations:
        return AnalyzerResult("level_effectiveness", 0.5, 0.0, {}, ("learning_history_not_available",))
    names = sorted({name for item in observations for name in item.level_scores})
    if not names:
        return AnalyzerResult("level_effectiveness", 0.5, 0.0, {}, ("level_history_not_available",))
    values = [sum(item.level_scores.get(name, 0.5) for item in observations) / len(observations) for name in names]
    return AnalyzerResult("level_effectiveness", sum(values) / len(values), min(1.0, len(observations) / 20.0), {"levels": names})
