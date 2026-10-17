from bot.intelligence.levels.level_14.analyzers import (
    anomaly_contradiction,
    conviction_trap,
    data_reliability,
    risk_contradiction,
    scenario_contradiction,
    signal_contradiction,
)
from bot.intelligence.levels.level_14.models.level_14_result import Level14Result


class Level14Engine:
    # The first five analyzers measure contradiction; data_reliability is a
    # quality gate and must not raise the contradiction score when data is clean.
    CONTRADICTION_WEIGHTS = (0.20, 0.18, 0.18, 0.16, 0.16)
    _WEIGHT_TOTAL = sum(CONTRADICTION_WEIGHTS)

    def analyze(self, level6_result, level10_result, level12_result, level13_result) -> Level14Result:
        results = (
            signal_contradiction.analyze(level10_result, level13_result),
            conviction_trap.analyze(level10_result, level12_result),
            risk_contradiction.analyze(level6_result, level10_result),
            anomaly_contradiction.analyze(level12_result, level10_result),
            scenario_contradiction.analyze(level13_result, level10_result),
        )
        reliability = data_reliability.analyze(level10_result, level12_result, level13_result)

        score = sum(result.score * weight for result, weight in zip(results, self.CONTRADICTION_WEIGHTS)) / self._WEIGHT_TOTAL
        source_confidence = sum(result.confidence * weight for result, weight in zip(results, self.CONTRADICTION_WEIGHTS)) / self._WEIGHT_TOTAL
        # Reliability limits confidence in the contradiction assessment, but is
        # not itself a contradiction signal.
        confidence = source_confidence * reliability.score
        scores = [result.score for result in results]
        consistency = 1.0 - (max(scores) - min(scores)) if any(result.confidence > 0 for result in results) else 0.0
        all_results = results + (reliability,)

        return Level14Result(
            symbol=level10_result.symbol,
            score=max(0.0, min(1.0, score)),
            confidence=max(0.0, min(1.0, confidence)),
            consistency=max(0.0, min(1.0, consistency)),
            signal_contradiction=results[0].score,
            conviction_trap=results[1].score,
            risk_contradiction=results[2].score,
            anomaly_contradiction=results[3].score,
            scenario_contradiction=results[4].score,
            data_reliability=reliability.score,
            analyzer_results=all_results,
            warnings=tuple(dict.fromkeys(w for result in all_results for w in result.warnings)),
            metadata={
                "version": "1.1",
                "trade_decision": False,
                "contradiction_weights_normalized": True,
                "reliability_applied_to_confidence": True,
            },
        )
