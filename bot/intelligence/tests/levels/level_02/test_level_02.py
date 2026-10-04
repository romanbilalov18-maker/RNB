import unittest

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.level_01_engine import analyze as analyze_level_1
from bot.intelligence.levels.level_02.level_02_engine import analyze as analyze_level_2
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


class Level02EngineTests(unittest.TestCase):
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

    def test_returns_level_2_contract(self):
        result = analyze_level_2(self.snapshot, self.level1)
        self.assertIsInstance(result, Level2Result)
        self.assertEqual(result.symbol, "TEST")
        self.assertEqual(len(result.analyzer_results), 6)

    def test_score_confidence_and_consistency_are_bounded(self):
        result = analyze_level_2(self.snapshot, self.level1)
        for value in (result.score, result.confidence, result.consistency):
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_level_2_consumes_level_1_without_mutating_it(self):
        before = self.level1
        analyze_level_2(self.snapshot, self.level1)
        self.assertEqual(before, self.level1)

    def test_missing_data_produces_warnings_instead_of_crashing(self):
        snapshot = MarketSnapshot(symbol="TEST", price=100.0)
        level1 = analyze_level_1(snapshot)
        result = analyze_level_2(snapshot, level1)
        self.assertTrue(result.warnings)


if __name__ == "__main__":
    unittest.main()
