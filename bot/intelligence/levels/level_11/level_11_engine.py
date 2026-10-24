from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.levels.level_11.analyzers import (
    analyzer_effectiveness,
    learning_confidence,
    level_effectiveness,
    outcome_quality,
    regime_adaptation,
    weight_adaptation,
)
from bot.intelligence.levels.level_11.models.learning_observation import LearningObservation
from bot.intelligence.levels.level_11.models.level_11_result import Level11Result


class Level11Engine:
    WEIGHTS = (0.20, 0.20, 0.18, 0.14, 0.14, 0.14)

    def analyze(self, symbol: str, observations: tuple[LearningObservation, ...] = ()) -> Level11Result:
        results = (
            outcome_quality.analyze(observations),
            level_effectiveness.analyze(observations),
            analyzer_effectiveness.analyze(observations),
            regime_adaptation.analyze(observations),
            weight_adaptation.analyze(observations),
        )
        confidence = learning_confidence.analyze(observations, results)
        all_results = results + (confidence,)

        # A zero-confidence analyzer has no usable evidence. Exclude it from
        # aggregate score and consistency rather than treating its default
        # score (often 0.0) as a negative learning result.
        available = tuple(
            (result, weight)
            for result, weight in zip(all_results, self.WEIGHTS)
            if result.confidence > 0.0
        )
        available_weight = sum(weight for _, weight in available)
        score = (
            sum(result.score * weight for result, weight in available) / available_weight
            if available_weight > 0.0 else 0.0
        )
        overall_confidence = (
            sum(result.confidence for result, _ in available) / len(available)
            if available else 0.0
        )
        available_scores = [result.score for result, _ in available]
        consistency = (
            1.0 - (max(available_scores) - min(available_scores))
            if available_scores else 0.0
        )
        return Level11Result(
            symbol=symbol,
            score=max(0.0, min(1.0, score)),
            confidence=max(0.0, min(1.0, overall_confidence)),
            consistency=max(0.0, min(1.0, consistency)),
            outcome_quality=results[0].score,
            level_effectiveness=results[1].score,
            analyzer_effectiveness=results[2].score,
            regime_adaptation=results[3].score,
            weight_adaptation=results[4].score,
            learning_confidence=confidence.score,
            sample_count=len(observations),
            analyzer_results=all_results,
            warnings=tuple(dict.fromkeys(w for result in all_results for w in result.warnings)),
            proposed_level_weights=dict(results[4].metrics.get("proposed_level_weights", {})),
            proposed_analyzer_weights=dict(results[4].metrics.get("proposed_analyzer_weights", {})),
            metadata={
                "version": "1.1",
                "adaptive_weights_are_proposals": True,
                "weights_applied_to_trading": False,
                "proposal_status": results[4].metrics.get("proposal_status", "insufficient_history"),
                "aggregation_excludes_zero_confidence": True,
            },
        )
