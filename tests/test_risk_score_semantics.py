import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_06.level_06_engine import Level6Engine
from bot.intelligence.levels.level_07.level_07_engine import Level7Engine
from bot.intelligence.levels.level_09.level_09_engine import Level9Engine


class RiskScoreSemanticsTests(unittest.TestCase):
    def test_level6_higher_downside_and_volatility_risk_reduce_quality(self):
        snapshot = MarketSnapshot(symbol="AAA", price=100.0)
        level5 = SimpleNamespace(score=0.6, confidence=0.9)

        def result(name, score, confidence=1.0):
            return AnalyzerResult(name, score, confidence)

        def run(downside, volatility, adverse):
            with (
                patch("bot.intelligence.levels.level_06.level_06_engine.downside_risk.analyze",
                     return_value=result("downside_risk", downside)),
                patch("bot.intelligence.levels.level_06.level_06_engine.volatility_risk.analyze",
                     return_value=result("volatility_risk", volatility)),
                patch("bot.intelligence.levels.level_06.level_06_engine.reward_potential.analyze",
                     return_value=result("reward_potential", 0.6)),
                patch("bot.intelligence.levels.level_06.level_06_engine.risk_reward.analyze",
                     return_value=result("risk_reward", 0.6)),
                patch("bot.intelligence.levels.level_06.level_06_engine.adverse_scenario.analyze",
                     return_value=result("adverse_scenario", adverse)),
                patch("bot.intelligence.levels.level_06.level_06_engine.risk_consistency.analyze",
                     return_value=result("risk_consistency", 0.8)),
            ):
                return Level6Engine().analyze(snapshot, level5)

        safer = run(downside=0.1, volatility=0.1, adverse=0.1)
        riskier = run(downside=0.9, volatility=0.9, adverse=0.9)

        self.assertLess(riskier.score, safer.score)
        self.assertEqual(riskier.downside_risk, 0.9)
        self.assertEqual(riskier.volatility_risk, 0.9)

    def test_level7_higher_exhaustion_transition_and_anomaly_reduce_quality(self):
        snapshot = MarketSnapshot(symbol="AAA", price=100.0)
        level3 = SimpleNamespace(score=0.6, confidence=0.9, consistency=0.8)
        level4 = SimpleNamespace(confidence=0.9, abnormal_activity=0.4)
        level5 = SimpleNamespace(confidence=0.9, consistency=0.8, signal_stability=0.8)
        level6 = SimpleNamespace(confidence=0.9, consistency=0.8)

        def result(name, score, confidence=1.0):
            return AnalyzerResult(name, score, confidence)

        def run(exhaustion, transition, anomaly):
            with (
                patch("bot.intelligence.levels.level_07.level_07_engine.momentum_acceleration.analyze",
                     return_value=result("momentum_acceleration", 0.6)),
                patch("bot.intelligence.levels.level_07.level_07_engine.trend_persistence.analyze",
                     return_value=result("trend_persistence", 0.6)),
                patch("bot.intelligence.levels.level_07.level_07_engine.movement_exhaustion.analyze",
                     return_value=result("movement_exhaustion", exhaustion)),
                patch("bot.intelligence.levels.level_07.level_07_engine.regime_transition.analyze",
                     return_value=result("regime_transition", transition)),
                patch("bot.intelligence.levels.level_07.level_07_engine.temporal_anomaly.analyze",
                     return_value=result("temporal_anomaly", anomaly)),
                patch("bot.intelligence.levels.level_07.level_07_engine.dynamic_stability.analyze",
                     return_value=result("dynamic_stability", 0.8)),
            ):
                return Level7Engine().analyze(snapshot, level3, level4, level5, level6)

        safer = run(exhaustion=0.1, transition=0.1, anomaly=0.1)
        riskier = run(exhaustion=0.9, transition=0.9, anomaly=0.9)

        self.assertLess(riskier.score, safer.score)
        self.assertEqual(riskier.movement_exhaustion, 0.9)
        self.assertEqual(riskier.regime_transition, 0.9)
        self.assertEqual(riskier.temporal_anomaly, 0.9)

    def test_level9_higher_concentration_and_correlation_reduce_quality(self):
        snapshot = MarketSnapshot(symbol="AAA", price=100.0)
        level5 = SimpleNamespace(symbol="AAA", score=0.6, confidence=0.9)
        level6 = SimpleNamespace(symbol="AAA", score=0.6, risk_reward=0.6, confidence=0.9)
        level8 = SimpleNamespace(symbol="AAA", score=0.6, confidence=0.9)

        def result(name, score, confidence=1.0):
            return AnalyzerResult(name, score, confidence)

        def run(concentration, correlation):
            with (
                patch("bot.intelligence.levels.level_09.level_09_engine.concentration_risk.analyze",
                     return_value=result("concentration_risk", concentration)),
                patch("bot.intelligence.levels.level_09.level_09_engine.diversification_value.analyze",
                     return_value=result("diversification_value", 0.6)),
                patch("bot.intelligence.levels.level_09.level_09_engine.portfolio_compatibility.analyze",
                     return_value=result("portfolio_compatibility", 0.6)),
                patch("bot.intelligence.levels.level_09.level_09_engine.correlation_risk.analyze",
                     return_value=result("correlation_risk", correlation)),
                patch("bot.intelligence.levels.level_09.level_09_engine.opportunity_priority.analyze",
                     return_value=result("opportunity_priority", 0.6)),
                patch("bot.intelligence.levels.level_09.level_09_engine.portfolio_consistency.analyze",
                     return_value=result("portfolio_consistency", 0.8)),
            ):
                return Level9Engine().analyze(snapshot, level5, level6, level8)

        safer = run(concentration=0.1, correlation=0.1)
        riskier = run(concentration=0.9, correlation=0.9)

        self.assertLess(riskier.score, safer.score)
        self.assertEqual(riskier.concentration_risk, 0.9)
        self.assertEqual(riskier.correlation_risk, 0.9)


if __name__ == "__main__":
    unittest.main()
