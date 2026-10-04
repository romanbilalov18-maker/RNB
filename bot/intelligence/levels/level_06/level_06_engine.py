from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from .analyzers import downside_risk, volatility_risk, reward_potential, risk_reward, adverse_scenario, risk_consistency
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
        results = {
            "downside_risk": downside_risk.analyze(snapshot, level5_result),
            "volatility_risk": volatility_risk.analyze(snapshot),
            "reward_potential": reward_potential.analyze(snapshot, level5_result),
        }
        results["risk_reward"] = risk_reward.analyze(results["downside_risk"], results["reward_potential"])
        results["adverse_scenario"] = adverse_scenario.analyze(snapshot, level5_result)
        results["risk_consistency"] = risk_consistency.analyze(level5_result, results["downside_risk"], results["risk_reward"])
        score = sum(results[k].score * w for k, w in self.WEIGHTS.items())
        confidence = sum(r.confidence for r in results.values()) / len(results)
        consistency = results["risk_consistency"].score
        warnings = list(dict.fromkeys(w for r in results.values() for w in r.warnings))
        strengths, weaknesses = [], []
        if results["risk_reward"].score >= 0.65: strengths.append("favorable_risk_reward")
        if results["downside_risk"].score >= 0.65: weaknesses.append("elevated_downside_risk")
        if results["adverse_scenario"].score >= 0.65: weaknesses.append("adverse_scenario_material")
        return Level6Result(
            symbol=snapshot.symbol, score=max(0.0, min(1.0, score)), confidence=max(0.0, min(1.0, confidence)),
            consistency=consistency, downside_risk=results["downside_risk"].score,
            volatility_risk=results["volatility_risk"].score, reward_potential=results["reward_potential"].score,
            risk_reward=results["risk_reward"].score, adverse_scenario=results["adverse_scenario"].score,
            risk_consistency=results["risk_consistency"].score, analyzer_results=results,
            strengths=strengths, weaknesses=weaknesses, warnings=warnings, metadata={"version": "1.0"},
        )
