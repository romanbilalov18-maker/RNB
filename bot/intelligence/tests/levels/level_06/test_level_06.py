import unittest
from dataclasses import replace
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.levels.level_01.level_01_engine import Level1Engine
from bot.intelligence.levels.level_02.level_02_engine import Level2Engine
from bot.intelligence.levels.level_03.level_03_engine import Level3Engine
from bot.intelligence.levels.level_04.level_04_engine import Level4Engine
from bot.intelligence.levels.level_05.level_05_engine import Level5Engine
from bot.intelligence.levels.level_06.level_06_engine import Level6Engine
from bot.intelligence.levels.level_06.analyzers.risk_reward import analyze as analyze_risk_reward


class TestLevel6(unittest.TestCase):
    def setUp(self):
        s = MarketSnapshot("TEST", 105.0, 100.0, 1500.0, 1000.0, 0.02, 0.03, 0.8)
        l1 = Level1Engine().analyze(s)
        l2 = Level2Engine().analyze(s, l1)
        l3 = Level3Engine().analyze(s, l2)
        l4 = Level4Engine().analyze(s, l3)
        self.snapshot, self.l5 = s, Level5Engine().analyze(s, l2, l3, l4)

    def test_all_six_analyzers_run(self):
        result = Level6Engine().analyze(self.snapshot, self.l5)
        self.assertEqual(len(result.analyzer_results), 6)
        self.assertTrue(0.0 <= result.score <= 1.0)
        self.assertTrue(0.0 <= result.confidence <= 1.0)

    def test_risk_reward_is_bounded(self):
        result = Level6Engine().analyze(self.snapshot, self.l5)
        self.assertTrue(0.0 <= result.risk_reward <= 1.0)

    def test_high_volatility_increases_volatility_risk(self):
        normal = Level6Engine().analyze(self.snapshot, self.l5)
        high = MarketSnapshot("TEST", 105.0, 100.0, 1500.0, 1000.0, 0.10, 0.03, 0.8)
        high_result = Level6Engine().analyze(high, self.l5)
        self.assertGreater(high_result.volatility_risk, normal.volatility_risk)

    def test_does_not_mutate_inputs(self):
        before = self.l5
        Level6Engine().analyze(self.snapshot, self.l5)
        self.assertEqual(before, self.l5)

    def test_level5_symbol_mismatch_disables_aggregate(self):
        mismatched = replace(self.l5, symbol="OTHER")
        result = Level6Engine().analyze(self.snapshot, mismatched)
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("level5_symbol_mismatch", result.warnings)
        self.assertFalse(result.metadata["level5_context_valid"])

    def test_non_finite_volatility_is_unavailable(self):
        invalid = replace(self.snapshot, volatility=float("nan"))
        result = Level6Engine().analyze(invalid, self.l5)
        self.assertEqual(result.analyzer_results["volatility_risk"].confidence, 0.0)
        self.assertIn("volatility_input_invalid", result.warnings)

    def test_missing_level5_context_does_not_crash(self):
        result = Level6Engine().analyze(self.snapshot, None)
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("level5_context_not_available", result.warnings)

    def test_zero_risk_and_reward_is_not_presented_as_valid_ratio(self):
        risk = AnalyzerResult("risk", 0.0, 1.0)
        reward = AnalyzerResult("reward", 0.0, 1.0)
        result = analyze_risk_reward(risk, reward)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("risk_reward_both_components_zero", result.warnings)


if __name__ == "__main__":
    unittest.main()
