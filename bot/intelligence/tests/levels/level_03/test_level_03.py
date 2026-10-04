import unittest

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.level_01_engine import analyze as analyze_level_1
from bot.intelligence.levels.level_02.level_02_engine import analyze as analyze_level_2
from bot.intelligence.levels.level_03.level_03_engine import analyze as analyze_level_3
from bot.intelligence.levels.level_03.models.level_03_result import Level3Result


class Level03EngineTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = MarketSnapshot(
            symbol="TEST",
            price=105.0,
            previous_price=100.0,
            volume=200.0,
            average_volume=100.0,
            volatility=0.10,
            momentum=0.02,
            liquidity=0.80,
        )
        self.level1 = analyze_level_1(self.snapshot)
        self.level2 = analyze_level_2(self.snapshot, self.level1)

    def test_returns_level_3_contract(self):
        result = analyze_level_3(self.snapshot, self.level2)
        self.assertIsInstance(result, Level3Result)
        self.assertEqual(result.symbol, "TEST")
        self.assertEqual(len(result.analyzer_results), 6)

    def test_score_confidence_and_consistency_are_bounded(self):
        result = analyze_level_3(self.snapshot, self.level2)
        for value in (result.score, result.confidence, result.consistency):
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_external_context_is_neutral_when_unavailable(self):
        result = analyze_level_3(self.snapshot, self.level2)
        names = {r.analyzer for r in result.analyzer_results}
        self.assertIn("macro_context", names)
        self.assertIn("sector_context", names)
        self.assertTrue(result.warnings)

    def test_level_3_does_not_mutate_level_2(self):
        before = self.level2
        analyze_level_3(self.snapshot, self.level2)
        self.assertEqual(before, self.level2)

    def test_missing_data_does_not_crash(self):
        snapshot = MarketSnapshot(symbol="TEST", price=100.0)
        level1 = analyze_level_1(snapshot)
        level2 = analyze_level_2(snapshot, level1)
        result = analyze_level_3(snapshot, level2)
        self.assertIsInstance(result, Level3Result)
        self.assertTrue(result.warnings)


if __name__ == "__main__":
    unittest.main()
