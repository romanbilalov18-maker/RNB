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
    WEIGHTS = (0.20, 0.18, 0.18, 0.16, 0.16, 0.12)

    def analyze(self, level6_result, level10_result, level12_result, level13_result) -> Level14Result:
        results = (
            signal_contradiction.analyze(level10_result, level13_result),
            conviction_trap.analyze(level10_result, level12_result),
            risk_contradiction.analyze(level6_result, level10_result),
            anomaly_contradiction.analyze(level12_result, level10_result),
            scenario_contradiction.analyze(level13_result, level10_result),
            data_reliability.analyze(level10_result, level12_result, level13_result),
        )
        score = sum(result.score * weight for result, weight in zip(results, self.WEIGHTS))
        confidence = sum(result.confidence for result in results) / len(results)
        consistency = 1.0 - (max(result.score for result in results) - min(result.score for result in results))
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
            data_reliability=results[5].score,
            analyzer_results=results,
            warnings=tuple(dict.fromkeys(w for result in results for w in result.warnings)),
            metadata={"version": "1.0", "trade_decision": False},
        )
