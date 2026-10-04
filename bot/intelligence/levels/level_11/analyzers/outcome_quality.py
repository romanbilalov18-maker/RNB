from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(observations) -> AnalyzerResult:
    if not observations:
        return AnalyzerResult("outcome_quality", 0.5, 0.0, {"sample_count": 0}, ("learning_history_not_available",))
    correct_ratio = sum(1 for item in observations if item.correct) / len(observations)
    return AnalyzerResult("outcome_quality", correct_ratio, min(1.0, len(observations) / 20.0), {"sample_count": len(observations)})
