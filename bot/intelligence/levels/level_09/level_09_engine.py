from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from .analyzers import concentration_risk, diversification_value, portfolio_compatibility, correlation_risk, opportunity_priority, portfolio_consistency
from .models.level_09_result import Level9Result


class Level9Engine:
    WEIGHTS = {
        "concentration_risk": 0.16,
        "diversification_value": 0.16,
        "portfolio_compatibility": 0.18,
        "correlation_risk": 0.16,
        "opportunity_priority": 0.20,
        "portfolio_consistency": 0.14,
    }

    def analyze(self, snapshot: MarketSnapshot, level5_result, level6_result, level8_result) -> Level9Result:
        results = {
            "concentration_risk": concentration_risk.analyze(snapshot, level6_result),
            "diversification_value": diversification_value.analyze(level8_result),
            "portfolio_compatibility": portfolio_compatibility.analyze(level5_result, level8_result),
            "correlation_risk": correlation_risk.analyze(level8_result, level6_result),
            "opportunity_priority": opportunity_priority.analyze(level5_result, level6_result, level8_result),
            "portfolio_consistency": portfolio_consistency.analyze(level5_result, level6_result, level8_result),
        }
        score = sum(results[k].score * w for k, w in self.WEIGHTS.items())
        confidence = sum(r.confidence for r in results.values()) / len(results)
        consistency = results["portfolio_consistency"].score
        warnings = list(dict.fromkeys(w for r in results.values() for w in r.warnings))
        strengths, weaknesses = [], []
        if results["opportunity_priority"].score >= 0.7: strengths.append("high_opportunity_priority")
        if results["diversification_value"].score >= 0.7: strengths.append("potential_diversification_value")
        if results["concentration_risk"].score >= 0.7: weaknesses.append("elevated_concentration_risk")
        if results["correlation_risk"].score >= 0.7: weaknesses.append("elevated_correlation_risk")
        return Level9Result(
            symbol=snapshot.symbol, score=max(0.0, min(1.0, score)), confidence=max(0.0, min(1.0, confidence)),
            consistency=consistency, concentration_risk=results["concentration_risk"].score,
            diversification_value=results["diversification_value"].score, portfolio_compatibility=results["portfolio_compatibility"].score,
            correlation_risk=results["correlation_risk"].score, opportunity_priority=results["opportunity_priority"].score,
            portfolio_consistency=results["portfolio_consistency"].score, analyzer_results=results,
            strengths=strengths, weaknesses=weaknesses, warnings=warnings, metadata={"version": "1.0"},
        )
