import unittest
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.level_01_engine import Level1Engine
from bot.intelligence.levels.level_02.level_02_engine import Level2Engine
from bot.intelligence.levels.level_03.level_03_engine import Level3Engine
from bot.intelligence.levels.level_04.level_04_engine import Level4Engine
from bot.intelligence.levels.level_05.level_05_engine import Level5Engine
from bot.intelligence.levels.level_06.level_06_engine import Level6Engine
from bot.intelligence.levels.level_07.level_07_engine import Level7Engine
from bot.intelligence.levels.level_08.level_08_engine import Level8Engine


class TestLevel8(unittest.TestCase):
    def setUp(self):
        s = MarketSnapshot("TEST", 105.0, 100.0, 1500.0, 1000.0, 0.02, 0.03, 0.8)
        l1 = Level1Engine().analyze(s); l2 = Level2Engine().analyze(s, l1); l3 = Level3Engine().analyze(s, l2)
        l4 = Level4Engine().analyze(s, l3); l5 = Level5Engine().analyze(s, l2, l3, l4); l6 = Level6Engine().analyze(s, l5)
        l7 = Level7Engine().analyze(s, l3, l4, l5, l6)
        self.snapshot, self.l3, self.l4, self.l7 = s, l3, l4, l7

    def test_all_six_analyzers_run(self):
        result = Level8Engine().analyze(self.snapshot, self.l3, self.l4, self.l7)
        self.assertEqual(len(result.analyzer_results), 6)
        self.assertTrue(0.0 <= result.score <= 1.0)
        self.assertTrue(0.0 <= result.confidence <= 1.0)

    def test_relative_scores_are_bounded(self):
        result = Level8Engine().analyze(self.snapshot, self.l3, self.l4, self.l7)
        for value in (result.market_relative_strength, result.sector_relative_strength, result.peer_context, result.cross_asset_context, result.benchmark_alignment, result.relative_consistency):
            self.assertTrue(0.0 <= value <= 1.0)

    def test_missing_external_data_is_explicit(self):
        result = Level8Engine().analyze(self.snapshot, self.l3, self.l4, self.l7)
        self.assertIn("cross_asset_data_not_available", result.warnings)
        self.assertIn("sector_data_not_available", result.warnings)

    def test_does_not_mutate_inputs(self):
        before = (self.l3, self.l4, self.l7)
        Level8Engine().analyze(self.snapshot, *before)
        self.assertEqual(before, (self.l3, self.l4, self.l7))


if __name__ == "__main__":
    unittest.main()
