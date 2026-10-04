from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from .analyzers import conviction, cross_level_agreement, confidence_quality, risk_adjusted_conviction, warning_impact, decision_readiness
from .models.level_10_result import Level10Result


class Level10Engine:
    WEIGHTS = {
        "conviction": 0.20,
        "cross_level_agreement": 0.20,
        "confidence_quality": 0.15,
        "risk_adjusted_conviction": 0.20,
        "warning_impact": 0.10,
        "decision_readiness": 0.15,
    }

    def analyze(self, snapshot: MarketSnapshot, level5_result, level6_result, level7_result, level8_result, level9_result) -> Level10Result:
        results = {
            "conviction": conviction.analyze(level5_result, level6_result, level7_result, level8_result, level9_result),
            "cross_level_agreement": cross_level_agreement.analyze(level5_result, level6_result, level7_result, level8_result, level9_result),
            "confidence_quality": confidence_quality.analyze(level5_result, level6_result, level7_result, level8_result, level9_result),
            "risk_adjusted_conviction": risk_adjusted_conviction.analyze(level5_result, level6_result, level9_result),
            "warning_impact": warning_impact.analyze(level5_result, level6_result, level7_result, level8_result, level9_result),
        }
        results["decision_readiness"] = decision_readiness.analyze(*results.values())
        score = sum(results[k].score * w for k, w in self.WEIGHTS.items())
        confidence = sum(r.confidence for r in results.values()) / len(results)
        consistency = results["cross_level_agreement"].score
        warnings = list(dict.fromkeys(w for r in results.values() for w in r.warnings))
        strengths, weaknesses = [], []
        if results["decision_readiness"].score >= 0.7: strengths.append("high_decision_readiness")
        if results["cross_level_agreement"].score >= 0.7: strengths.append("strong_cross_level_agreement")
        if results["risk_adjusted_conviction"].score < 0.5: weaknesses.append("weak_risk_adjusted_conviction")
        if results["warning_impact"].score < 0.7: weaknesses.append("material_warnings")
        return Level10Result(
            symbol=snapshot.symbol, score=max(0.0, min(1.0, score)), confidence=max(0.0, min(1.0, confidence)), consistency=consistency,
            conviction=results["conviction"].score, cross_level_agreement=results["cross_level_agreement"].score,
            confidence_quality=results["confidence_quality"].score, risk_adjusted_conviction=results["risk_adjusted_conviction"].score,
            warning_impact=results["warning_impact"].score, decision_readiness=results["decision_readiness"].score,
            analyzer_results=results, strengths=strengths, weaknesses=weaknesses, warnings=warnings, metadata={"version": "1.0"},
        )
