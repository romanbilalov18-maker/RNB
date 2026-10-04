from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from .analyzers import signal_strength, signal_confirmation, signal_conflict, signal_consistency, signal_stability, reliability
from .models.level_05_result import Level5Result


class Level5Engine:
    WEIGHTS = {
        "signal_strength": 0.22,
        "signal_confirmation": 0.18,
        "signal_conflict": 0.18,
        "signal_consistency": 0.16,
        "signal_stability": 0.12,
        "reliability": 0.14,
    }

    def analyze(self, snapshot: MarketSnapshot, level2_result, level3_result, level4_result) -> Level5Result:
        results = {
            "signal_strength": signal_strength.analyze(level3_result, level4_result),
            "signal_confirmation": signal_confirmation.analyze(level2_result, level4_result),
            "signal_conflict": signal_conflict.analyze(level3_result, level4_result),
            "signal_consistency": signal_consistency.analyze(level2_result, level3_result, level4_result),
            "signal_stability": signal_stability.analyze(level3_result, level4_result),
            "reliability": reliability.analyze(level3_result, level4_result),
        }
        score = sum(results[k].score * w for k, w in self.WEIGHTS.items())
        confidence = sum(r.confidence for r in results.values()) / len(results)
        consistency = results["signal_consistency"].score
        warnings = list(dict.fromkeys(w for r in results.values() for w in r.warnings))
        strengths, weaknesses = [], []
        if results["signal_strength"].score >= 0.7: strengths.append("strong_signal")
        if results["signal_confirmation"].score >= 0.7: strengths.append("multi_level_confirmation")
        if results["signal_conflict"].score < 0.5: weaknesses.append("signal_conflict")
        if results["reliability"].score < 0.5: weaknesses.append("low_reliability")
        return Level5Result(
            symbol=snapshot.symbol, score=max(0.0, min(1.0, score)), confidence=max(0.0, min(1.0, confidence)),
            consistency=consistency, signal_strength=results["signal_strength"].score,
            signal_confirmation=results["signal_confirmation"].score, signal_conflict=results["signal_conflict"].score,
            signal_consistency=results["signal_consistency"].score, signal_stability=results["signal_stability"].score,
            reliability=results["reliability"].score, analyzer_results=results,
            strengths=strengths, weaknesses=weaknesses, warnings=warnings, metadata={"version": "1.0"},
        )
