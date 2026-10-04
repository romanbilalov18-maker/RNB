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
        master = master_confidence.analyze(results)
        score = sum(result.score * weight for result, weight in zip(results, self.WEIGHTS))
        confidence = sum(result.confidence for result in results) / len(results)
        consistency = 1.0 - (max(result.score for result in results) - min(result.score for result in results))
        return Level15Result(
            symbol=l10.symbol,
            score=max(0.0, min(1.0, score)),
            confidence=max(0.0, min(1.0, confidence)),
            consistency=max(0.0, min(1.0, consistency)),
            signal_quality=results[0].score,
            risk_quality=results[1].score,
            scenario_quality=results[2].score,
            anomaly_quality=results[3].score,
            adversarial_resilience=results[4].score,
            learning_quality=results[5].score,
            master_confidence=master.score,
            analyzer_results=results + (master,),
            warnings=tuple(dict.fromkeys(w for result in results + (master,) for w in result.warnings)),
            metadata={"version": "1.0", "master_synthesis": True, "trade_decision": False},
        )
