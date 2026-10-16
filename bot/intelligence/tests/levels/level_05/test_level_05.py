import unittest
from dataclasses import replace
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.level_02_engine import Level2Engine
from bot.intelligence.levels.level_03.level_03_engine import Level3Engine
from bot.intelligence.levels.level_04.level_04_engine import Level4Engine
from bot.intelligence.levels.level_05.level_05_engine import Level5Engine


class TestLevel5(unittest.TestCase):
    def setUp(self):
        self.snapshot = MarketSnapshot("TEST", 105.0, 100.0, 1500.0, 1000.0, 0.02, 0.03, 0.8)
        self.l1 = __import__("bot.intelligence.levels.level_01.level_01_engine", fromlist=["Level1Engine"]).Level1Engine().analyze(self.snapshot)
        self.l2 = Level2Engine().analyze(self.snapshot, self.l1)
        self.l3 = Level3Engine().analyze(self.snapshot, self.l2)
        self.l4 = Level4Engine().analyze(self.snapshot, self.l3)

    def test_all_six_analyzers_run(self):
        result = Level5Engine().analyze(self.snapshot, self.l2, self.l3, self.l4)
        self.assertEqual(len(result.analyzer_results), 6)
        self.assertTrue(0.0 <= result.score <= 1.0)
        self.assertTrue(0.0 <= result.confidence <= 1.0)

    def test_consistency_is_bounded(self):
        result = Level5Engine().analyze(self.snapshot, self.l2, self.l3, self.l4)
        self.assertTrue(0.0 <= result.consistency <= 1.0)

    def test_conflict_is_explicit(self):
        result = Level5Engine().analyze(self.snapshot, self.l2, self.l3, self.l4)
        self.assertIn("signal_conflict", result.analyzer_results)

    def test_does_not_mutate_inputs(self):
        before = (self.l2, self.l3, self.l4)
        Level5Engine().analyze(self.snapshot, self.l2, self.l3, self.l4)
        self.assertEqual(before, (self.l2, self.l3, self.l4))

    def test_symbol_mismatch_disables_aggregate_signal(self):
        mismatched = replace(self.l3, symbol="OTHER")
        result = Level5Engine().analyze(self.snapshot, self.l2, mismatched, self.l4)
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("level3_symbol_mismatch", result.warnings)
        self.assertFalse(result.metadata["cross_level_context_valid"])

    def test_non_finite_score_is_not_treated_as_valid_signal(self):
        malformed = replace(self.l4, score=float("nan"))
        result = Level5Engine().analyze(self.snapshot, self.l2, self.l3, malformed)
        self.assertEqual(result.analyzer_results["signal_strength"].score, 0.0)
        self.assertEqual(result.analyzer_results["signal_strength"].confidence, 0.0)
        self.assertIn("signal_strength_inputs_invalid", result.warnings)

    def test_missing_context_is_reported_not_crashed(self):
        result = Level5Engine().analyze(self.snapshot, self.l2, None, self.l4)
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("level3_context_not_available", result.warnings)


if __name__ == "__main__":
    unittest.main()
