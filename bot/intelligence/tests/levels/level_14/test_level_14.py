import unittest
from dataclasses import replace
from unittest.mock import patch

from bot.intelligence.core.models.analysis_result import AnalyzerResult
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
from bot.intelligence.levels.level_14 import level_14_engine
from bot.intelligence.levels.level_14.analyzers.data_reliability import analyze as analyze_data_reliability
from bot.intelligence.levels.level_14.level_14_engine import Level14Engine
from bot.intelligence.levels.level_14.models.level_14_result import Level14Result


class TestLevel14(unittest.TestCase):
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
        l12 = Level12Engine().analyze(snapshot, l4, l7, l10)
        l13 = Level13Engine().analyze(snapshot, l6, l7, l10, l12)
        self.inputs = (l6, l10, l12, l13)

    def test_analyzes_five_contradictions_and_reliability_diagnostic(self):
        result = Level14Engine().analyze(*self.inputs)
        self.assertEqual(len(result.analyzer_results), 6)
        self.assertEqual([r.analyzer for r in result.analyzer_results],
                         ["signal_contradiction", "conviction_trap", "risk_contradiction",
                          "anomaly_contradiction", "scenario_contradiction", "data_reliability"])
        self.assertTrue(0.0 <= result.score <= 1.0)
        self.assertTrue(0.0 <= result.confidence <= 1.0)

    def test_reliability_uses_data_anomaly_and_all_source_confidences(self):
        level6, l10, l12, l13 = self.inputs
        low_anomaly = replace(l12, data_anomaly=0.0, warnings=())
        high_anomaly = replace(l12, data_anomaly=1.0, warnings=())
        clean = analyze_data_reliability(l10, low_anomaly, l13)
        unreliable = analyze_data_reliability(l10, high_anomaly, l13)
        self.assertEqual(clean.score, 1.0)
        self.assertEqual(unreliable.score, 0.0)
        low_confidence_l13 = replace(l13, confidence=0.05)
        self.assertEqual(analyze_data_reliability(l10, low_anomaly, low_confidence_l13).confidence, 0.05)

    def test_reliability_does_not_increase_contradiction_score(self):
        engine = Level14Engine()
        unreliable = AnalyzerResult("data_reliability", 0.0, 0.5)
        reliable = AnalyzerResult("data_reliability", 1.0, 0.5)
        with patch.object(level_14_engine.data_reliability, "analyze", return_value=unreliable):
            low = engine.analyze(*self.inputs)
        with patch.object(level_14_engine.data_reliability, "analyze", return_value=reliable):
            high = engine.analyze(*self.inputs)
        self.assertAlmostEqual(low.score, high.score)
        self.assertLessEqual(low.confidence, high.confidence)

    def test_result_rejects_nonfinite_and_boolean_metrics(self):
        base = dict(symbol="TEST", score=0.5, confidence=0.5, consistency=0.5,
                    signal_contradiction=0.5, conviction_trap=0.5, risk_contradiction=0.5,
                    anomaly_contradiction=0.5, scenario_contradiction=0.5, data_reliability=0.5)
        for bad in (float("nan"), float("inf"), True):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                Level14Result(**{**base, "score": bad})

    def test_does_not_create_trade_decision(self):
        result = Level14Engine().analyze(*self.inputs)
        self.assertFalse(hasattr(result, "buy"))
        self.assertFalse(hasattr(result, "sell"))
        self.assertFalse(hasattr(result, "action"))


if __name__ == "__main__":
    unittest.main()
