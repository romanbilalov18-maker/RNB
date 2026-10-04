from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from .analyzers import momentum_acceleration, trend_persistence, movement_exhaustion, regime_transition, temporal_anomaly, dynamic_stability
from .models.level_07_result import Level7Result


class Level7Engine:
    WEIGHTS = {
        "momentum_acceleration": 0.18,
        "trend_persistence": 0.20,
        "movement_exhaustion": 0.16,
        "regime_transition": 0.16,
        "temporal_anomaly": 0.14,
        "dynamic_stability": 0.16,
    }

    def analyze(self, snapshot: MarketSnapshot, level3_result, level4_result, level5_result, level6_result) -> Level7Result:
        results = {
            "momentum_acceleration": momentum_acceleration.analyze(snapshot, level6_result),
            "trend_persistence": trend_persistence.analyze(snapshot, level3_result),
            "movement_exhaustion": movement_exhaustion.analyze(snapshot, level6_result),
            "regime_transition": regime_transition.analyze(snapshot, level3_result),
            "temporal_anomaly": temporal_anomaly.analyze(snapshot, level4_result),
            "dynamic_stability": dynamic_stability.analyze(level5_result, level6_result),
        }
        score = sum(results[k].score * w for k, w in self.WEIGHTS.items())
        confidence = sum(r.confidence for r in results.values()) / len(results)
        consistency = min(1.0, max(0.0, (level5_result.consistency + level6_result.consistency) / 2.0))
        warnings = list(dict.fromkeys(w for r in results.values() for w in r.warnings))
        strengths, weaknesses = [], []
        if results["trend_persistence"].score >= 0.7: strengths.append("persistent_trend")
        if results["momentum_acceleration"].score >= 0.7: strengths.append("positive_dynamic_acceleration")
        if results["movement_exhaustion"].score >= 0.7: weaknesses.append("movement_exhaustion_risk")
        if results["regime_transition"].score >= 0.7: weaknesses.append("regime_transition_detected")
        return Level7Result(
            symbol=snapshot.symbol, score=max(0.0, min(1.0, score)), confidence=max(0.0, min(1.0, confidence)),
            consistency=consistency, momentum_acceleration=results["momentum_acceleration"].score,
            trend_persistence=results["trend_persistence"].score, movement_exhaustion=results["movement_exhaustion"].score,
            regime_transition=results["regime_transition"].score, temporal_anomaly=results["temporal_anomaly"].score,
            dynamic_stability=results["dynamic_stability"].score, analyzer_results=results,
            strengths=strengths, weaknesses=weaknesses, warnings=warnings, metadata={"version": "1.0"},
        )
