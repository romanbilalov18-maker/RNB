import unittest

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.level_01_engine import analyze as analyze_level_01, aggregate
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result
from bot.intelligence.levels.level_02.level_02_engine import analyze as analyze_level_02
from bot.intelligence.levels.level_03.level_03_engine import analyze as analyze_level_03
from bot.intelligence.levels.level_04.level_04_engine import Level4Engine
from bot.intelligence.levels.level_05.level_05_engine import Level5Engine
from bot.intelligence.levels.level_06.level_06_engine import Level6Engine
from bot.intelligence.levels.level_07.level_07_engine import Level7Engine
from bot.intelligence.levels.level_08.level_08_engine import Level8Engine
from bot.intelligence.levels.level_09.level_09_engine import Level9Engine
from bot.intelligence.levels.level_10.level_10_engine import Level10Engine
from bot.intelligence.levels.level_12.level_12_engine import Level12Engine
from bot.intelligence.levels.level_13.level_13_engine import Level13Engine
from bot.intelligence.levels.level_14.level_14_engine import Level14Engine
from bot.intelligence.levels.level_11.level_11_engine import Level11Engine
from bot.intelligence.levels.level_15.level_15_engine import Level15Engine


class TestLevel15(unittest.TestCase):
    def setUp(self):
        snapshot = MarketSnapshot("TEST", 105.0, 100.0, 1500.0, 1000.0, 0.02, 0.04, 0.85)
        a = analyze_level_01(snapshot)
        l1 = Level1Result("TEST", aggregate(a), sum(x.confidence for x in a) / len(a), 0.8, a)
        l2 = analyze_level_02(snapshot, l1)
        l3 = analyze_level_03(snapshot, l2)
        l4 = Level4Engine().analyze(snapshot, l3)
        l5 = Level5Engine().analyze(snapshot, l2, l3, l4)
        l6 = Level6Engine().analyze(snapshot, l5)
        l7 = Level7Engine().analyze(snapshot, l3, l4, l5, l6)
        l8 = Level8Engine().analyze(snapshot, l3, l4, l7)
        l9 = Level9Engine().analyze(snapshot, l5, l6, l8)
        l10 = Level10Engine().analyze(snapshot, l5, l6, l7, l8, l9)
        l11 = Level11Engine().analyze("TEST")
        l12 = Level12Engine().analyze(snapshot, l4, l7, l10)
        l13 = Level13Engine().analyze(snapshot, l6, l7, l10, l12)
        l14 = Level14Engine().analyze(l6, l10, l12, l13)
        self.inputs = (l6, l10, l11, l12, l13, l14)

    def test_master_synthesis(self):
        result = Level15Engine().analyze(*self.inputs)
        self.assertEqual(len(result.analyzer_results), 7)
        self.assertTrue(0.0 <= result.score <= 1.0)
        self.assertTrue(0.0 <= result.master_confidence <= 1.0)

    def test_does_not_create_trade_decision(self):
        result = Level15Engine().analyze(*self.inputs)
        self.assertFalse(hasattr(result, "buy"))
        self.assertFalse(hasattr(result, "sell"))
        self.assertFalse(hasattr(result, "action"))


if __name__ == "__main__":
    unittest.main()
