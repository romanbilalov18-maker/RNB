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
        context_warnings = []
        for name, result in (("level5", level5_result), ("level6", level6_result), ("level8", level8_result)):
            if result is None:
                context_warnings.append(f"{name}_context_not_available")
                continue
            symbol = getattr(result, "symbol", None)
            if not isinstance(symbol, str) or not symbol:
                context_warnings.append(f"{name}_symbol_not_available")
            elif symbol != snapshot.symbol:
                context_warnings.append(f"{name}_symbol_mismatch")

        results = {
            "concentration_risk": concentration_risk.analyze(snapshot, level6_result),
            "diversification_value": diversification_value.analyze(snapshot, level8_result),
            "portfolio_compatibility": portfolio_compatibility.analyze(snapshot, level5_result, level8_result),
            "correlation_risk": correlation_risk.analyze(snapshot, level8_result, level6_result),
            "opportunity_priority": opportunity_priority.analyze(level5_result, level6_result, level8_result),
            "portfolio_consistency": portfolio_consistency.analyze(level5_result, level6_result, level8_result),
        }
        quality_scores = {
            "concentration_risk": 1.0 - results["concentration_risk"].score,
            "diversification_value": results["diversification_value"].score,
            "portfolio_compatibility": results["portfolio_compatibility"].score,
            "correlation_risk": 1.0 - results["correlation_risk"].score,
            "opportunity_priority": results["opportunity_priority"].score,
            "portfolio_consistency": results["portfolio_consistency"].score,
        }
        effective = {
            key: self.WEIGHTS[key] * max(0.0, min(1.0, results[key].confidence))
            for key in self.WEIGHTS
        }
        total_effective = sum(effective.values())
        score = (
            sum(quality_scores[key] * weight for key, weight in effective.items()) / total_effective
            if total_effective > 0 else 0.0
        )
        confidence = sum(
            self.WEIGHTS[key] * max(0.0, min(1.0, results[key].confidence))
            for key in self.WEIGHTS
        ) / sum(self.WEIGHTS.values())
        if context_warnings:
            score = 0.0
            confidence = 0.0

        consistency = results["portfolio_consistency"].score
        warnings = list(dict.fromkeys(context_warnings + [w for r in results.values() for w in r.warnings]))
        strengths, weaknesses = [], []
        if not context_warnings and results["opportunity_priority"].confidence > 0 and results["opportunity_priority"].score >= 0.7:
            strengths.append("high_opportunity_priority")
        if results["diversification_value"].confidence > 0 and results["diversification_value"].score >= 0.7:
            strengths.append("potential_diversification_value")
        if results["concentration_risk"].confidence > 0 and results["concentration_risk"].score >= 0.7:
            weaknesses.append("elevated_concentration_risk")
        if results["correlation_risk"].confidence > 0 and results["correlation_risk"].score >= 0.7:
            weaknesses.append("elevated_correlation_risk")
        if context_warnings:
            weaknesses.append("invalid_cross_level_context")
        return Level9Result(
            symbol=snapshot.symbol, score=max(0.0, min(1.0, score)), confidence=max(0.0, min(1.0, confidence)),
            consistency=consistency, concentration_risk=results["concentration_risk"].score,
            diversification_value=results["diversification_value"].score, portfolio_compatibility=results["portfolio_compatibility"].score,
            correlation_risk=results["correlation_risk"].score, opportunity_priority=results["opportunity_priority"].score,
            portfolio_consistency=results["portfolio_consistency"].score, analyzer_results=results,
            strengths=strengths, weaknesses=weaknesses, warnings=warnings,
            metadata={"version": "1.1", "cross_level_context_valid": not context_warnings},
        )
