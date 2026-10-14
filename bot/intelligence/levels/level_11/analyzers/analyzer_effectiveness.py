from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.levels.level_11.analyzers.predictive_skill import (
    effectiveness_score,
    feature_predictive_metrics,
)


def analyze(observations) -> AnalyzerResult:
    if not observations:
        return AnalyzerResult("analyzer_effectiveness", 0.5, 0.0, {}, ("learning_history_not_available",))
    metrics = feature_predictive_metrics(observations, "analyzer_scores")
    if not metrics:
        return AnalyzerResult("analyzer_effectiveness", 0.5, 0.0, {}, ("analyzer_history_not_available",))
    return AnalyzerResult(
        "analyzer_effectiveness",
        effectiveness_score(metrics),
        min(1.0, len(observations) / 30.0),
        {"analyzers": metrics, "method": "score_outcome_correlation"},
    )
