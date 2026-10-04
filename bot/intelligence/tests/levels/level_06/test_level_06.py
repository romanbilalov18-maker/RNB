import unittest
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.level_01_engine import Level1Engine
from bot.intelligence.levels.level_02.level_02_engine import Level2Engine
from bot.intelligence.levels.level_03.level_03_engine import Level3Engine
from bot.intelligence.levels.level_04.level_04_engine import Level4Engine
from bot.intelligence.levels.level_05.level_05_engine import Level5Engine
from bot.intelligence.levels.level_06.level_06_engine import Level6Engine


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


if __name__ == "__main__":
    unittest.main()
