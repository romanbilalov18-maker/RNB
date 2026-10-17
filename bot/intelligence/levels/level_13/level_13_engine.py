from bot.intelligence.levels.level_13.analyzers import (
    adverse_scenario,
    continuation,
    neutral_scenario,
    reversal,
    scenario_confidence,
    volatility_expansion,
)
from bot.intelligence.levels.level_13.models.level_13_result import Level13Result


class Level13Engine:
    # These weights apply to the five actual scenario forecasts only.
    # Scenario confidence is a diagnostic about their agreement, not a sixth forecast.
    SCENARIO_WEIGHTS = (0.20, 0.18, 0.16, 0.18, 0.12)
    _WEIGHT_TOTAL = sum(SCENARIO_WEIGHTS)

    def analyze(self, snapshot, level6_result, level7_result, level10_result, level12_result) -> Level13Result:
        results = (
            continuation.analyze(snapshot, level7_result, level10_result),
            reversal.analyze(snapshot, level7_result, level10_result),
            volatility_expansion.analyze(snapshot, level6_result, level7_result),
            adverse_scenario.analyze(level6_result, level10_result, level12_result),
            neutral_scenario.analyze(level10_result, level12_result),
        )
        confidence_result = scenario_confidence.analyze(results)

        # Normalize the weights because the scenario-only weights sum to 0.84.
        score = sum(result.score * weight for result, weight in zip(results, self.SCENARIO_WEIGHTS)) / self._WEIGHT_TOTAL
        confidence = sum(result.confidence * weight for result, weight in zip(results, self.SCENARIO_WEIGHTS)) / self._WEIGHT_TOTAL

        # Agreement is calculated across forecasts only; the derived agreement metric
        # must not widen or narrow its own spread.
        scores = [result.score for result in results]
        consistency = 1.0 - (max(scores) - min(scores)) if any(result.confidence > 0 for result in results) else 0.0
        all_results = results + (confidence_result,)

        return Level13Result(
            symbol=snapshot.symbol,
            score=max(0.0, min(1.0, score)),
            confidence=max(0.0, min(1.0, confidence)),
            consistency=max(0.0, min(1.0, consistency)),
            continuation=results[0].score,
            reversal=results[1].score,
            volatility_expansion=results[2].score,
            adverse_scenario=results[3].score,
            neutral_scenario=results[4].score,
            scenario_confidence=confidence_result.score,
            analyzer_results=all_results,
            warnings=tuple(dict.fromkeys(w for result in all_results for w in result.warnings)),
            metadata={
                "version": "1.1",
                "forecast_is_probabilistic": True,
                "trade_decision": False,
                "score_weights_normalized": True,
                "scenario_count": len(results),
            },
        )
