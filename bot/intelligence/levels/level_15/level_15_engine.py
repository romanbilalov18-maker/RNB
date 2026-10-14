from bot.intelligence.levels.level_15.analyzers import (
    adversarial_resilience,
    anomaly_quality,
    learning_quality,
    master_confidence,
    risk_quality,
    scenario_quality,
    signal_quality,
)
from bot.intelligence.levels.level_15.models.level_15_result import Level15Result


class Level15Engine:
    WEIGHTS = (0.20, 0.18, 0.18, 0.12, 0.18, 0.14)

    def analyze(self, l6, l10, l11, l12, l13, l14) -> Level15Result:
        results = (
            signal_quality.analyze(l10),
            risk_quality.analyze(l6, l10),
            scenario_quality.analyze(l13),
            anomaly_quality.analyze(l12),
            adversarial_resilience.analyze(l14),
            learning_quality.analyze(l11),
        )

        # A missing evidence source is not evidence of poor quality. In
        # particular, L11 has no empirical score until forward outcomes mature.
        # Exclude unavailable analyzers from aggregation rather than assigning
        # their placeholder score a fixed share of the master score.
        observed = tuple(
            (result, weight)
            for result, weight in zip(results, self.WEIGHTS)
            if result.confidence > 0.0
        )
        if observed:
            observed_weight = sum(weight for _, weight in observed)
            observed_score = sum(result.score * weight for result, weight in observed) / observed_weight
            observed_confidence = sum(result.confidence * weight for result, weight in observed) / observed_weight
            master = master_confidence.analyze(tuple(result for result, _ in observed))
            score = 0.90 * observed_score + 0.10 * master.score
            confidence = 0.90 * observed_confidence + 0.10 * master.confidence
            consistency_scores = [result.score for result, _ in observed] + [master.score]
            consistency = 1.0 - (max(consistency_scores) - min(consistency_scores))
        else:
            master = master_confidence.analyze(())
            score = confidence = consistency = 0.0

        score = max(0.0, min(1.0, score))
        confidence = max(0.0, min(1.0, confidence))
        quality_analyzer_consistency = max(0.0, min(1.0, consistency))

        # Final consistency is about agreement between trading-analysis levels,
        # not the spread between L15's quality-analyzer scores.
        agreement_result = getattr(l10, "analyzer_results", {}).get("cross_level_agreement")
        agreement_confidence = (
            agreement_result.confidence if agreement_result is not None
            else getattr(l10, "confidence", 0.0)
        )
        consistency = (
            max(0.0, min(1.0, float(l10.cross_level_agreement)))
            if agreement_confidence > 0.0 else 0.0
        )
        confidence = min(confidence, max(0.0, min(1.0, float(agreement_confidence))))
        all_results = results + (master,)
        return Level15Result(
            symbol=l10.symbol,
            score=score,
            confidence=confidence,
            consistency=consistency,
            signal_quality=results[0].score,
            risk_quality=results[1].score,
            scenario_quality=results[2].score,
            anomaly_quality=results[3].score,
            adversarial_resilience=results[4].score,
            learning_quality=results[5].score,
            master_confidence=master.score,
            analyzer_results=all_results,
            warnings=tuple(dict.fromkeys(w for result in all_results for w in result.warnings)),
            metadata={
                "version": "1.2",
                "master_synthesis": True,
                "trade_decision": False,
                "consistency_source": "L10.cross_level_agreement",
                "quality_analyzer_consistency": quality_analyzer_consistency,
                "excluded_unavailable_analyzers": tuple(
                    result.analyzer for result in results if result.confidence <= 0.0
                ),
            },
        )
