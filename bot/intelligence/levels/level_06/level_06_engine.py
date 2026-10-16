from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from .analyzers import downside_risk, volatility_risk, reward_potential, risk_reward, adverse_scenario, risk_consistency
from .analyzers._validation import number
from .models.level_06_result import Level6Result


class Level6Engine:
    WEIGHTS = {
        "downside_risk": 0.20,
        "volatility_risk": 0.15,
        "reward_potential": 0.20,
        "risk_reward": 0.20,
        "adverse_scenario": 0.15,
        "risk_consistency": 0.10,
    }

    def analyze(self, snapshot: MarketSnapshot, level5_result) -> Level6Result:
        context_warnings = []
        if level5_result is None:
            context_warnings.append("level5_context_not_available")
        else:
            symbol = getattr(level5_result, "symbol", None)
            if not isinstance(symbol, str) or not symbol:
                context_warnings.append("level5_symbol_not_available")
            elif symbol != snapshot.symbol:
                context_warnings.append("level5_symbol_mismatch")
            if number(getattr(level5_result, "score", None), minimum=0.0, maximum=1.0) is None:
                context_warnings.append("level5_score_invalid")
            if number(getattr(level5_result, "confidence", None), minimum=0.0, maximum=1.0) is None:
                context_warnings.append("level5_confidence_invalid")

        results = {
            "downside_risk": downside_risk.analyze(snapshot, level5_result),
            "volatility_risk": volatility_risk.analyze(snapshot),
            "reward_potential": reward_potential.analyze(snapshot, level5_result),
        }
        results["risk_reward"] = risk_reward.analyze(results["downside_risk"], results["reward_potential"])
        results["adverse_scenario"] = adverse_scenario.analyze(snapshot, level5_result)
        results["risk_consistency"] = risk_consistency.analyze(level5_result, results["downside_risk"], results["risk_reward"])

        # Risk severity is higher-is-worse; aggregate score is higher-is-better.
        quality_scores = {
            "downside_risk": 1.0 - results["downside_risk"].score,
            "volatility_risk": 1.0 - results["volatility_risk"].score,
            "reward_potential": results["reward_potential"].score,
            "risk_reward": results["risk_reward"].score,
            "adverse_scenario": 1.0 - results["adverse_scenario"].score,
            "risk_consistency": results["risk_consistency"].score,
        }
        effective_weights = {
            key: weight * max(0.0, min(1.0, results[key].confidence))
            for key, weight in self.WEIGHTS.items()
        }
        effective_total = sum(effective_weights.values())
        score = (
            sum(quality_scores[key] * weight for key, weight in effective_weights.items()) / effective_total
            if effective_total > 0 else 0.0
        )
        confidence = sum(
            self.WEIGHTS[key] * max(0.0, min(1.0, result.confidence))
            for key, result in results.items()
        ) / sum(self.WEIGHTS.values())
        consistency = results["risk_consistency"].score
        warnings = list(dict.fromkeys(context_warnings + [w for result in results.values() for w in result.warnings]))
        strengths, weaknesses = [], []
        if not context_warnings and results["risk_reward"].score >= 0.65:
            strengths.append("favorable_risk_reward")
        if results["downside_risk"].score >= 0.65:
            weaknesses.append("elevated_downside_risk")
        if results["adverse_scenario"].score >= 0.65:
            weaknesses.append("adverse_scenario_material")
        if context_warnings:
            score = 0.0
            confidence = 0.0
            weaknesses.append("invalid_level5_context")
        return Level6Result(
            symbol=snapshot.symbol, score=max(0.0, min(1.0, score)),
            confidence=max(0.0, min(1.0, confidence)), consistency=consistency,
            downside_risk=results["downside_risk"].score,
            volatility_risk=results["volatility_risk"].score,
            reward_potential=results["reward_potential"].score,
            risk_reward=results["risk_reward"].score,
            adverse_scenario=results["adverse_scenario"].score,
            risk_consistency=results["risk_consistency"].score,
            analyzer_results=results, strengths=strengths, weaknesses=weaknesses,
            warnings=warnings,
            metadata={"version": "1.1", "level5_context_valid": not context_warnings},
        )
