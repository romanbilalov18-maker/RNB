from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(observations) -> AnalyzerResult:
    if not observations:
        return AnalyzerResult("weight_adaptation", 0.5, 0.0, {}, ("learning_history_not_available",))
    dispersion = []
    for item in observations:
        values = list(item.level_scores.values())
        if values:
            dispersion.append(max(values) - min(values))
    score = 1.0 - (sum(dispersion) / len(dispersion) if dispersion else 0.5)
    return AnalyzerResult("weight_adaptation", max(0.0, min(1.0, score)), min(1.0, len(observations) / 20.0))
