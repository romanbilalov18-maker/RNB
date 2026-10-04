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
        score = sum(results[k].score * w for k, w in self.WEIGHTS.items())
        confidences = [r.confidence for r in results.values()]
        confidence = sum(confidences) / len(confidences)
        spread = max(r.score for r in results.values()) - min(r.score for r in results.values())
        consistency = max(0.0, 1.0 - spread)
        warnings = [w for r in results.values() for w in r.warnings]
        strengths, weaknesses = [], []
        if balance >= 0.65: strengths.append("buying_pressure_dominant")
        if balance <= 0.35: weaknesses.append("selling_pressure_dominant")
        if results["abnormal_activity"].score >= 0.7: strengths.append("abnormal_activity_detected")
        if results["liquidity_behavior"].score < 0.35: weaknesses.append("weak_liquidity_behavior")
        return Level4Result(
            symbol=snapshot.symbol, score=score, confidence=confidence, consistency=consistency,
            buying_pressure=buy, selling_pressure=sell, pressure_balance=balance,
            accumulation=results["accumulation"].score, distribution=results["distribution"].score,
            abnormal_activity=results["abnormal_activity"].score,
            liquidity_behavior=results["liquidity_behavior"].score,
            analyzer_results=results, strengths=strengths, weaknesses=weaknesses,
            warnings=list(dict.fromkeys(warnings)), metadata={"version": "1.0"},
        )
