from bot.intelligence.levels.level_12.analyzers import (
    behavior_anomaly,
    data_anomaly,
    price_anomaly,
    signal_anomaly,
    volatility_anomaly,
    volume_anomaly,
)
from bot.intelligence.levels.level_12.models.level_12_result import Level12Result


class Level12Engine:
    WEIGHTS = (0.18, 0.18, 0.16, 0.18, 0.16, 0.14)

    def analyze(self, snapshot, level4_result, level7_result, level10_result) -> Level12Result:
        results = (
            price_anomaly.analyze(snapshot),
            volume_anomaly.analyze(snapshot),
            volatility_anomaly.analyze(snapshot),
            behavior_anomaly.analyze(level4_result),
            signal_anomaly.analyze(level7_result, level10_result),
            data_anomaly.analyze(snapshot),
        )
        score = sum(result.score * weight for result, weight in zip(results, self.WEIGHTS))
        confidence = sum(result.confidence for result in results) / len(results)
        consistency = 1.0 - (max(result.score for result in results) - min(result.score for result in results))
        return Level12Result(
            symbol=snapshot.symbol,
            score=max(0.0, min(1.0, score)),
            confidence=max(0.0, min(1.0, confidence)),
            consistency=max(0.0, min(1.0, consistency)),
            price_anomaly=results[0].score,
            volume_anomaly=results[1].score,
            volatility_anomaly=results[2].score,
            behavior_anomaly=results[3].score,
            signal_anomaly=results[4].score,
            data_anomaly=results[5].score,
            analyzer_results=results,
            warnings=tuple(dict.fromkeys(w for result in results for w in result.warnings)),
            metadata={"version": "1.0", "trade_decision": False},
        )
