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
        inputs = (("level2", level2_result), ("level3", level3_result), ("level4", level4_result))
        symbol_warnings = []
        for name, result in inputs:
            if result is None:
                symbol_warnings.append(f"{name}_context_not_available")
                continue
            symbol = getattr(result, "symbol", None)
            if not isinstance(symbol, str) or not symbol:
                symbol_warnings.append(f"{name}_symbol_not_available")
            elif symbol != snapshot.symbol:
                symbol_warnings.append(f"{name}_symbol_mismatch")

        results = {
            "signal_strength": signal_strength.analyze(level3_result, level4_result),
            "signal_confirmation": signal_confirmation.analyze(level2_result, level4_result),
            "signal_conflict": signal_conflict.analyze(level3_result, level4_result),
            "signal_consistency": signal_consistency.analyze(level2_result, level3_result, level4_result),
            "signal_stability": signal_stability.analyze(level3_result, level4_result),
            "reliability": reliability.analyze(level3_result, level4_result),
        }
        warnings = list(dict.fromkeys(symbol_warnings + [w for result in results.values() for w in result.warnings]))
        invalid_context = bool(symbol_warnings)
        score = sum(results[key].score * weight for key, weight in self.WEIGHTS.items())
        confidence = sum(result.confidence for result in results.values()) / len(results)
        consistency = results["signal_consistency"].score
        strengths, weaknesses = [], []
        if not invalid_context:
            if results["signal_strength"].score >= 0.7:
                strengths.append("strong_signal")
            if results["signal_confirmation"].score >= 0.7:
                strengths.append("multi_level_confirmation")
        if results["signal_conflict"].score < 0.5:
            weaknesses.append("signal_conflict")
        if results["reliability"].score < 0.5:
            weaknesses.append("low_reliability")
        if invalid_context:
            score = 0.0
            confidence = 0.0
            weaknesses.append("invalid_cross_level_context")
        return Level5Result(
            symbol=snapshot.symbol,
            score=max(0.0, min(1.0, score)),
            confidence=max(0.0, min(1.0, confidence)),
            consistency=consistency,
            signal_strength=results["signal_strength"].score,
            signal_confirmation=results["signal_confirmation"].score,
            signal_conflict=results["signal_conflict"].score,
            signal_consistency=results["signal_consistency"].score,
            signal_stability=results["signal_stability"].score,
            reliability=results["reliability"].score,
            analyzer_results=results,
            strengths=strengths,
            weaknesses=weaknesses,
            warnings=warnings,
            metadata={"version": "1.1", "cross_level_context_valid": not invalid_context},
        )
