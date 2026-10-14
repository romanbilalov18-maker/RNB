import unittest
from types import SimpleNamespace

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_06.analyzers import adverse_scenario, downside_risk, volatility_risk
from bot.intelligence.levels.level_06.level_06_engine import Level6Engine
from bot.intelligence.levels.level_12.level_12_engine import Level12Engine
from bot.intelligence.levels.level_12.analyzers.data_anomaly import analyze as analyze_data_anomaly


class RiskDataConfidenceTests(unittest.TestCase):
    def test_risk_analyzers_do_not_claim_confidence_without_required_data(self):
        snapshot = MarketSnapshot(symbol="AAA", price=100.0)
        level5 = SimpleNamespace(score=0.6, confidence=0.8)

        volatility = volatility_risk.analyze(snapshot)
        downside = downside_risk.analyze(snapshot, level5)
        adverse = adverse_scenario.analyze(snapshot, level5)

        self.assertEqual(volatility.confidence, 0.0)
        self.assertEqual(downside.confidence, 0.0)
        self.assertEqual(adverse.confidence, 0.0)
        self.assertIn("volatility_data_not_available", volatility.warnings)
        self.assertIn("volatility_and_momentum_not_available", downside.warnings)
        self.assertIn("adverse_scenario_inputs_not_available", adverse.warnings)

    def test_partial_downside_inputs_reduce_confidence(self):
        snapshot = MarketSnapshot(symbol="AAA", price=100.0, volatility=0.02)
        level5 = SimpleNamespace(score=0.6, confidence=0.8)

        result = downside_risk.analyze(snapshot, level5)

        self.assertAlmostEqual(result.confidence, 0.4)
        self.assertIn("downside_risk_partial_inputs", result.warnings)
        self.assertAlmostEqual(result.score, 0.24)

    def test_level6_confidence_is_weighted_by_evidence(self):
        snapshot = MarketSnapshot(symbol="AAA", price=100.0)
        level5 = SimpleNamespace(score=0.6, confidence=0.8, signal_confirmation=None)

        result = Level6Engine().analyze(snapshot, level5)

        self.assertLess(result.confidence, 0.5)
        self.assertEqual(result.analyzer_results["volatility_risk"].confidence, 0.0)
        self.assertEqual(result.analyzer_results["downside_risk"].confidence, 0.0)

    def test_level12_score_ignores_unavailable_anomaly_analyzers(self):
        from unittest.mock import patch
        from bot.intelligence.core.models.analysis_result import AnalyzerResult

        snapshot = MarketSnapshot(symbol="AAA", price=100.0, previous_price=100.0)
        level4 = SimpleNamespace(
            confidence=0.8, abnormal_activity=0.2,
            buying_pressure=0.5, selling_pressure=0.5,
        )
        level7 = SimpleNamespace(confidence=0.8, regime_transition=0.5)
        level10 = SimpleNamespace(confidence=0.8, decision_readiness=0.5)

        with (
            patch("bot.intelligence.levels.level_12.level_12_engine.price_anomaly.analyze",
                 return_value=AnalyzerResult("price_anomaly", 0.8, 1.0)),
            patch("bot.intelligence.levels.level_12.level_12_engine.volume_anomaly.analyze",
                 return_value=AnalyzerResult("volume_anomaly", 0.0, 0.0)),
            patch("bot.intelligence.levels.level_12.level_12_engine.volatility_anomaly.analyze",
                 return_value=AnalyzerResult("volatility_anomaly", 0.0, 0.0)),
            patch("bot.intelligence.levels.level_12.level_12_engine.behavior_anomaly.analyze",
                 return_value=AnalyzerResult("behavior_anomaly", 0.0, 0.0)),
            patch("bot.intelligence.levels.level_12.level_12_engine.signal_anomaly.analyze",
                 return_value=AnalyzerResult("signal_anomaly", 0.0, 0.0)),
            patch("bot.intelligence.levels.level_12.level_12_engine.data_anomaly.analyze",
                 return_value=AnalyzerResult("data_anomaly", 0.0, 0.0)),
        ):
            result = Level12Engine().analyze(snapshot, level4, level7, level10)

        self.assertAlmostEqual(result.score, 0.8)
        self.assertAlmostEqual(result.confidence, 0.18)
        self.assertAlmostEqual(result.consistency, 1.0)


    def test_data_anomaly_detects_invalid_ohlc_and_nonpositive_volume_baseline(self):
        snapshot = MarketSnapshot(
            symbol="AAA",
            price=100.0,
            previous_price=99.0,
            volume=1000.0,
            average_volume=0.0,
            volatility=0.02,
            momentum=0.01,
            liquidity=0.7,
            open_price=105.0,
            high_price=103.0,
            low_price=98.0,
            close_price=100.0,
        )

        result = analyze_data_anomaly(snapshot)

        self.assertIn("average_volume", result.metrics["invalid_fields"])
        self.assertIn("inconsistent_ohlc", result.metrics["invalid_fields"])
        self.assertIn("market_snapshot_invalid_values", result.warnings)
        self.assertGreater(result.score, 0.0)


if __name__ == "__main__":
    unittest.main()
