import math

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from .analyzers import buying_pressure, selling_pressure, accumulation, distribution, abnormal_activity, liquidity_behavior
from .models.level_04_result import Level4Result


class Level4Engine:
    WEIGHTS = {
        "buying_pressure": 0.18,
        "selling_pressure": 0.18,
        "accumulation": 0.16,
        "distribution": 0.16,
        "abnormal_activity": 0.16,
        "liquidity_behavior": 0.16,
    }

    def analyze(self, snapshot: MarketSnapshot, level3_result=None) -> Level4Result:
        results = {
            "buying_pressure": buying_pressure.analyze(snapshot),
            "selling_pressure": selling_pressure.analyze(snapshot),
            "accumulation": accumulation.analyze(snapshot),
            "distribution": distribution.analyze(snapshot),
            "abnormal_activity": abnormal_activity.analyze(snapshot),
            "liquidity_behavior": liquidity_behavior.analyze(snapshot),
        }
        buy = results["buying_pressure"].score
        sell = results["selling_pressure"].score
        balance = (buy - sell + 1.0) / 2.0
        effective = {
            key: weight * max(0.0, min(1.0, results[key].confidence))
            for key, weight in self.WEIGHTS.items()
        }
        total_effective = sum(effective.values())
        score = (
            sum(results[key].score * weight for key, weight in effective.items()) / total_effective
            if total_effective > 0 else 0.0
        )
        confidences = [r.confidence for r in results.values()]
        confidence = sum(confidences) / len(confidences) if confidences else 0.0
        observed = [r for r in results.values() if r.confidence > 0]
        spread = max((r.score for r in observed), default=0.0) - min((r.score for r in observed), default=0.0)
        consistency = max(0.0, 1.0 - spread) if observed else 0.0
        warnings = [w for r in results.values() for w in r.warnings]
        strengths, weaknesses = [], []
        if balance >= 0.65:
            strengths.append("buying_pressure_dominant")
        if balance <= 0.35:
            weaknesses.append("selling_pressure_dominant")
        if results["abnormal_activity"].confidence > 0 and results["abnormal_activity"].score >= 0.7:
            strengths.append("abnormal_activity_detected")
        if results["liquidity_behavior"].confidence > 0 and results["liquidity_behavior"].score < 0.35:
            weaknesses.append("weak_liquidity_behavior")

        metadata = {"version": "1.1", "analyzers": len(results)}
        if level3_result is None:
            warnings.append("level3_context_not_available")
            metadata["level3_context_available"] = False
        else:
            level3_symbol = getattr(level3_result, "symbol", None)
            if level3_symbol is not None and level3_symbol != snapshot.symbol:
                warnings.append("level3_symbol_mismatch")
                metadata["level3_context_available"] = False
            else:
                metadata["level3_context_available"] = True
                metadata["level3_score"] = getattr(level3_result, "score", None)
                metadata["level3_confidence"] = getattr(level3_result, "confidence", None)

        # Refuse non-finite output even if a future analyzer violates its contract.
        if not math.isfinite(score):
            score, confidence, consistency = 0.0, 0.0, 0.0
            warnings.append("level4_non_finite_aggregate")
        return Level4Result(
            symbol=snapshot.symbol, score=max(0.0, min(1.0, score)),
            confidence=max(0.0, min(1.0, confidence)), consistency=max(0.0, min(1.0, consistency)),
            buying_pressure=buy, selling_pressure=sell, pressure_balance=max(0.0, min(1.0, balance)),
            accumulation=results["accumulation"].score, distribution=results["distribution"].score,
            abnormal_activity=results["abnormal_activity"].score,
            liquidity_behavior=results["liquidity_behavior"].score,
            analyzer_results=results, strengths=strengths, weaknesses=weaknesses,
            warnings=list(dict.fromkeys(warnings)), metadata=metadata,
        )
