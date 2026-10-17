import math
import unittest
from dataclasses import replace

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.level_01_engine import Level1Engine
from bot.intelligence.levels.level_02.level_02_engine import Level2Engine
from bot.intelligence.levels.level_03.level_03_engine import Level3Engine
from bot.intelligence.levels.level_04.level_04_engine import Level4Engine
from bot.intelligence.levels.level_05.level_05_engine import Level5Engine
from bot.intelligence.levels.level_06.level_06_engine import Level6Engine
from bot.intelligence.levels.level_07.level_07_engine import Level7Engine
from bot.intelligence.levels.level_08.level_08_engine import Level8Engine
from bot.intelligence.levels.level_09.level_09_engine import Level9Engine
from bot.intelligence.levels.level_10.level_10_engine import Level10Engine


class TestLevel10(unittest.TestCase):
    def setUp(self):
        s = MarketSnapshot("TEST", 105.0, 100.0, 1500.0, 1000.0, 0.02, 0.03, 0.8)
        l1 = Level1Engine().analyze(s)
        l2 = Level2Engine().analyze(s, l1)
        l3 = Level3Engine().analyze(s, l2)
        l4 = Level4Engine().analyze(s, l3)
        l5 = Level5Engine().analyze(s, l2, l3, l4)
        l6 = Level6Engine().analyze(s, l5)
        l7 = Level7Engine().analyze(s, l3, l4, l5, l6)
        l8 = Level8Engine().analyze(s, l3, l4, l7)
        l9 = Level9Engine().analyze(s, l5, l6, l8)
        self.snapshot, self.levels = s, (l5, l6, l7, l8, l9)

    def test_all_six_analyzers_run(self):
        result = Level10Engine().analyze(self.snapshot, *self.levels)
        self.assertEqual(len(result.analyzer_results), 6)
        self.assertTrue(0.0 <= result.score <= 1.0)
        self.assertTrue(0.0 <= result.confidence <= 1.0)
        self.assertTrue(result.metadata["input_validation_passed"])

    def test_final_scores_are_bounded(self):
        result = Level10Engine().analyze(self.snapshot, *self.levels)
        for value in (
            result.conviction,
            result.cross_level_agreement,
            result.confidence_quality,
            result.risk_adjusted_conviction,
            result.warning_impact,
            result.decision_readiness,
        ):
            self.assertTrue(0.0 <= value <= 1.0)

    def test_decision_readiness_is_explicit(self):
        result = Level10Engine().analyze(self.snapshot, *self.levels)
        self.assertIn("decision_readiness", result.analyzer_results)

    def test_does_not_mutate_inputs(self):
        before = self.levels
        Level10Engine().analyze(self.snapshot, *before)
        self.assertEqual(before, self.levels)

    def test_rejects_symbol_mismatch_before_analysis(self):
        bad_level6 = replace(self.levels[1], symbol="OTHER")
        levels = (self.levels[0], bad_level6, *self.levels[2:])
        result = Level10Engine().analyze(self.snapshot, *levels)

        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("level6_symbol_mismatch", result.warnings)
        self.assertFalse(result.metadata["input_validation_passed"])
        self.assertIn("invalid_level10_input", result.weaknesses)

    def test_rejects_nan_in_score(self):
        bad_level5 = replace(self.levels[0], score=math.nan)
        levels = (bad_level5, *self.levels[1:])
        result = Level10Engine().analyze(self.snapshot, *levels)

        self.assertEqual(result.score, 0.0)
        self.assertIn("level5_score_invalid", result.warnings)
        self.assertFalse(result.metadata["input_validation_passed"])

    def test_rejects_infinite_and_out_of_range_analyzer_fields(self):
        bad_level6 = replace(self.levels[1], risk_reward=math.inf)
        bad_level9 = replace(self.levels[4], opportunity_priority=1.1)
        levels = (self.levels[0], bad_level6, self.levels[2], self.levels[3], bad_level9)
        result = Level10Engine().analyze(self.snapshot, *levels)

        self.assertIn("level6_risk_reward_invalid", result.warnings)
        self.assertIn("level9_opportunity_priority_invalid", result.warnings)
        self.assertEqual(result.confidence, 0.0)

    def test_rejects_non_numeric_confidence(self):
        bad_level7 = replace(self.levels[2], confidence="0.8")
        levels = (self.levels[0], self.levels[1], bad_level7, *self.levels[3:])
        result = Level10Engine().analyze(self.snapshot, *levels)

        self.assertIn("level7_confidence_invalid", result.warnings)
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.confidence, 0.0)

    def test_rejects_malformed_warning_collection(self):
        bad_level8 = replace(self.levels[3], warnings=None)
        levels = (*self.levels[:3], bad_level8, self.levels[4])
        result = Level10Engine().analyze(self.snapshot, *levels)

        self.assertIn("level8_warnings_invalid", result.warnings)
        self.assertEqual(result.score, 0.0)


if __name__ == "__main__":
    unittest.main()
