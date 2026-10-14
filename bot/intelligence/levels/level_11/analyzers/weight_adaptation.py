from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.levels.level_11.analyzers.predictive_skill import (
    feature_predictive_metrics,
    proposed_weights,
)


def analyze(observations) -> AnalyzerResult:
    if not observations:
        return AnalyzerResult("weight_adaptation", 0.0, 0.0, {
            "proposed_level_weights": {},
            "proposed_analyzer_weights": {},
            "proposal_status": "insufficient_history",
        }, ("learning_history_not_available",))

    level_metrics = feature_predictive_metrics(observations, "level_scores")
    analyzer_metrics = feature_predictive_metrics(observations, "analyzer_scores")
    level_weights = proposed_weights(level_metrics, len(observations))
    analyzer_weights = proposed_weights(analyzer_metrics, len(observations))
    has_proposal = bool(level_weights or analyzer_weights)
    warnings = () if has_proposal else ("adaptive_weight_proposal_not_ready",)
    status = "shadow_proposal_ready" if has_proposal else "insufficient_predictive_signal"
    all_metrics = (*level_metrics.values(), *analyzer_metrics.values())
    score = sum(item["effectiveness"] for item in all_metrics) / len(all_metrics) if all_metrics else 0.0
    return AnalyzerResult(
        "weight_adaptation",
        max(0.0, min(1.0, score)),
        min(1.0, len(observations) / 30.0) if all_metrics else 0.0,
        {
            "sample_count": len(observations),
            "proposed_level_weights": level_weights,
            "proposed_analyzer_weights": analyzer_weights,
            "level_predictive_metrics": level_metrics,
            "analyzer_predictive_metrics": analyzer_metrics,
            "proposal_status": status,
            "weights_applied_to_trading": False,
        },
        warnings,
    )
