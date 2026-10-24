import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.levels.level_13 import level_13_engine as l13_module
from bot.intelligence.levels.level_13.analyzers import scenario_confidence
from bot.intelligence.levels.level_13.level_13_engine import Level13Engine
from bot.intelligence.levels.level_14 import level_14_engine as l14_module
from bot.intelligence.levels.level_14.level_14_engine import Level14Engine


class MissingEvidenceAggregationTests(unittest.TestCase):
    def test_l13_excludes_unavailable_forecasts_from_score_and_consistency(self):
        snapshot = SimpleNamespace(symbol="TEST")
        forecast_results = [
            AnalyzerResult("continuation", 0.8, 0.9),
            AnalyzerResult("reversal", 0.1, 0.0),
            AnalyzerResult("volatility_expansion", 0.7, 0.8),
            AnalyzerResult("adverse_scenario", 0.2, 0.0),
            AnalyzerResult("neutral_scenario", 0.75, 0.7),
        ]
        patches = [
            patch.object(l13_module, name, SimpleNamespace(analyze=lambda *args, _result=result: _result))
            for name, result in zip(
                ("continuation", "reversal", "volatility_expansion", "adverse_scenario", "neutral_scenario"),
                forecast_results,
            )
        ]
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = Level13Engine().analyze(snapshot, None, None, None, None)

        weights = (0.20, 0.16, 0.12)
        expected_score = (0.8 * weights[0] + 0.7 * weights[1] + 0.75 * weights[2]) / sum(weights)
        self.assertAlmostEqual(result.score, expected_score)
        self.assertAlmostEqual(result.consistency, 1.0 - (0.8 - 0.7))
        self.assertGreater(result.confidence, 0.0)

    def test_l13_scenario_confidence_ignores_unavailable_forecast_outliers(self):
        results = (
            AnalyzerResult("available_a", 0.8, 0.8),
            AnalyzerResult("unavailable", 0.0, 0.0),
            AnalyzerResult("available_b", 0.7, 0.7),
        )
        result = scenario_confidence.analyze(results)
        self.assertAlmostEqual(result.score, 0.9)
        self.assertAlmostEqual(result.metrics["scenario_spread"], 0.1)

    def test_l14_excludes_unavailable_contradictions_from_score_and_consistency(self):
        contradiction_results = [
            AnalyzerResult("signal_contradiction", 0.2, 0.8),
            AnalyzerResult("conviction_trap", 1.0, 0.0),
            AnalyzerResult("risk_contradiction", 0.3, 0.7),
            AnalyzerResult("anomaly_contradiction", 0.0, 0.0),
            AnalyzerResult("scenario_contradiction", 0.25, 0.9),
        ]
        names = ("signal_contradiction", "conviction_trap", "risk_contradiction", "anomaly_contradiction", "scenario_contradiction")
        patches = [
            patch.object(l14_module, name, SimpleNamespace(analyze=lambda *args, _result=result: _result))
            for name, result in zip(names, contradiction_results)
        ]
        reliability = AnalyzerResult("data_reliability", 0.9, 0.9)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patch.object(
            l14_module, "data_reliability", SimpleNamespace(analyze=lambda *args: reliability)
        ):
            result = Level14Engine().analyze(None, SimpleNamespace(symbol="TEST"), None, None)

        weights = (0.20, 0.18, 0.16)
        expected_score = (0.2 * weights[0] + 0.3 * weights[1] + 0.25 * weights[2]) / sum(weights)
        self.assertAlmostEqual(result.score, expected_score)
        self.assertAlmostEqual(result.consistency, 0.9)
        self.assertGreater(result.confidence, 0.0)

    def test_l14_all_unavailable_contradictions_return_no_confidence(self):
        unavailable = AnalyzerResult("unavailable", 0.9, 0.0)
        names = ("signal_contradiction", "conviction_trap", "risk_contradiction", "anomaly_contradiction", "scenario_contradiction")
        patches = [
            patch.object(l14_module, name, SimpleNamespace(analyze=lambda *args, _result=unavailable: _result))
            for name in names
        ]
        reliability = AnalyzerResult("data_reliability", 1.0, 0.0)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patch.object(
            l14_module, "data_reliability", SimpleNamespace(analyze=lambda *args: reliability)
        ):
            result = Level14Engine().analyze(None, SimpleNamespace(symbol="TEST"), None, None)
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.consistency, 0.0)


if __name__ == "__main__":
    unittest.main()
