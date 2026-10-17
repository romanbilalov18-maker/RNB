import unittest
from dataclasses import replace
from unittest.mock import patch

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_13.analyzers.adverse_scenario import analyze as analyze_adverse_scenario
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
from bot.intelligence.levels.level_13 import level_13_engine
from bot.intelligence.levels.level_13.level_13_engine import Level13Engine
from bot.intelligence.levels.level_13.models.level_13_result import Level13Result


class TestLevel13(unittest.TestCase):
    def setUp(self):
        self.snapshot = MarketSnapshot("TEST", 105.0, 100.0, 1500.0, 1000.0, 0.02, 0.04, 0.85)
        analyzers = analyze_level_01(self.snapshot)
        l1 = Level1Result("TEST", aggregate(analyzers), sum(x.confidence for x in analyzers) / len(analyzers), 0.8, analyzers)
        l2 = analyze_level_02(self.snapshot, l1)
        l3 = analyze_level_03(self.snapshot, l2)
        l4 = Level4Engine().analyze(self.snapshot, l3)
        l5 = Level5Engine().analyze(self.snapshot, l2, l3, l4)
        l6 = Level6Engine().analyze(self.snapshot, l5)
        l7 = Level7Engine().analyze(self.snapshot, l3, l4, l5, l6)
        l8 = Level8Engine().analyze(self.snapshot, l3, l4, l7)
        l9 = Level9Engine().analyze(self.snapshot, l5, l6, l8)
        l10 = Level10Engine().analyze(self.snapshot, l5, l6, l7, l8, l9)
        l12 = Level12Engine().analyze(self.snapshot, l4, l7, l10)
        self.inputs = (l6, l7, l10, l12)

    def test_analyzes_five_scenarios_and_one_diagnostic(self):
        result = Level13Engine().analyze(self.snapshot, *self.inputs)
        self.assertEqual(len(result.analyzer_results), 6)
        self.assertEqual([x.analyzer for x in result.analyzer_results],
                         ["continuation", "reversal", "volatility_expansion",
                          "adverse_scenario", "neutral_scenario", "scenario_confidence"])
        self.assertTrue(0.0 <= result.score <= 1.0)
        self.assertTrue(0.0 <= result.confidence <= 1.0)

    def test_score_and_confidence_are_weighted_over_forecasts_only(self):
        engine = Level13Engine()
        result = engine.analyze(self.snapshot, *self.inputs)
        forecasts = result.analyzer_results[:5]
        total = sum(engine.SCENARIO_WEIGHTS)
        expected_score = sum(x.score * w for x, w in zip(forecasts, engine.SCENARIO_WEIGHTS)) / total
        expected_confidence = sum(x.confidence * w for x, w in zip(forecasts, engine.SCENARIO_WEIGHTS)) / total
        self.assertAlmostEqual(result.score, expected_score)
        self.assertAlmostEqual(result.confidence, expected_confidence)

    def test_derived_confidence_diagnostic_does_not_change_forecast_or_consistency(self):
        engine = Level13Engine()
        diagnostic_low = AnalyzerResult("scenario_confidence", 0.0, 0.0)
        diagnostic_high = AnalyzerResult("scenario_confidence", 1.0, 1.0)
        with patch.object(level_13_engine.scenario_confidence, "analyze", return_value=diagnostic_low):
            low = engine.analyze(self.snapshot, *self.inputs)
        with patch.object(level_13_engine.scenario_confidence, "analyze", return_value=diagnostic_high):
            high = engine.analyze(self.snapshot, *self.inputs)
        self.assertAlmostEqual(low.score, high.score)
        self.assertAlmostEqual(low.confidence, high.confidence)
        self.assertAlmostEqual(low.consistency, high.consistency)

    def test_detects_continuation_signal(self):
        result = Level13Engine().analyze(self.snapshot, *self.inputs)
        self.assertGreaterEqual(result.continuation, 0.0)

    def test_adverse_scenario_confidence_includes_l12_confidence(self):
        level6, _level7, level10, level12 = self.inputs
        uncertain_l12 = replace(level12, confidence=0.05)
        result = analyze_adverse_scenario(level6, level10, uncertain_l12)
        self.assertEqual(result.confidence, 0.05)

    def test_result_rejects_nonfinite_and_boolean_metrics(self):
        base = dict(symbol="TEST", score=0.5, confidence=0.5, consistency=0.5,
                    continuation=0.5, reversal=0.5, volatility_expansion=0.5,
                    adverse_scenario=0.5, neutral_scenario=0.5, scenario_confidence=0.5)
        for bad in (float("nan"), float("inf"), True):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                Level13Result(**{**base, "score": bad})

    def test_does_not_create_trade_decision(self):
        result = Level13Engine().analyze(self.snapshot, *self.inputs)
        self.assertFalse(hasattr(result, "buy"))
        self.assertFalse(hasattr(result, "sell"))
        self.assertFalse(hasattr(result, "action"))


if __name__ == "__main__":
    unittest.main()
