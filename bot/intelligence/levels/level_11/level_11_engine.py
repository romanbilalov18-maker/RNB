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
        score = sum(result.score * weight for result, weight in zip(all_results, self.WEIGHTS))
        overall_confidence = sum(result.confidence for result in all_results) / len(all_results)
        consistency = 1.0 - (max(result.score for result in all_results) - min(result.score for result in all_results))
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
            metadata={"version": "1.0", "adaptive_weights_are_proposals": True},
        )
