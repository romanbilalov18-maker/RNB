import math
import unittest
from dataclasses import replace

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_05.models.level_05_result import Level5Result
from bot.intelligence.levels.level_06.models.level_06_result import Level6Result
from bot.intelligence.levels.level_07.models.level_07_result import Level7Result
from bot.intelligence.levels.level_08.models.level_08_result import Level8Result
from bot.intelligence.levels.level_09.models.level_09_result import Level9Result
from bot.intelligence.levels.level_10.level_10_engine import Level10Engine


class TestLevel10(unittest.TestCase):
    def setUp(self):
        self.snapshot = MarketSnapshot("TEST", 105.0, 100.0, 1500.0, 1000.0, 0.02, 0.03, 0.8)
        self.levels = (
            Level5Result(
                symbol="TEST", score=0.72, confidence=0.80, consistency=0.70,
                signal_strength=0.72, signal_confirmation=0.80, signal_conflict=0.20,
                signal_consistency=0.70, signal_stability=0.65, reliability=0.80,
            ),
            Level6Result(
                symbol="TEST", score=0.68, confidence=0.75, consistency=0.70,
                downside_risk=0.30, volatility_risk=0.35, reward_potential=0.72,
                risk_reward=0.74, adverse_scenario=0.25, risk_consistency=0.70,
            ),
            Level7Result(
                symbol="TEST", score=0.70, confidence=0.78, consistency=0.70,
                momentum_acceleration=0.65, trend_persistence=0.72, movement_exhaustion=0.25,
                regime_transition=0.20, temporal_anomaly=0.10, dynamic_stability=0.75,
            ),
            Level8Result(
                symbol="TEST", score=0.73, confidence=0.76, consistency=0.72,
                market_relative_strength=0.72, sector_relative_strength=0.68,
                peer_context=0.70, cross_asset_context=0.67, benchmark_alignment=0.75,
                relative_consistency=0.72,
            ),
            Level9Result(
                symbol="TEST", score=0.69, confidence=0.74, consistency=0.70,
                concentration_risk=0.25, diversification_value=0.70,
                portfolio_compatibility=0.71, correlation_risk=0.28,
                opportunity_priority=0.73, portfolio_consistency=0.70,
            ),
        )

    def test_all_six_analyzers_run(self):
        result = Level10Engine().analyze(self.snapshot, *self.levels)
        self.assertEqual(len(result.analyzer_results), 6)
        self.assertTrue(0.0 <= result.score <= 1.0)
        self.assertTrue(0.0 <= result.confidence <= 1.0)
        self.assertTrue(result.metadata["input_validation_passed"])

    def test_final_scores_are_bounded(self):
        result = Level10Engine().analyze(self.snapshot, *self.levels)
        for value in (
            result.conviction,
            result.cross_level_agreement,
            result.confidence_quality,
            result.risk_adjusted_conviction,
            result.warning_impact,
            result.decision_readiness,
        ):
            self.assertTrue(0.0 <= value <= 1.0)

    def test_decision_readiness_is_explicit(self):
        result = Level10Engine().analyze(self.snapshot, *self.levels)
        self.assertIn("decision_readiness", result.analyzer_results)

    def test_does_not_mutate_inputs(self):
        before = self.levels
        Level10Engine().analyze(self.snapshot, *before)
        self.assertEqual(before, self.levels)

    def test_rejects_symbol_mismatch_before_analysis(self):
        bad_level6 = replace(self.levels[1], symbol="OTHER")
        levels = (self.levels[0], bad_level6, *self.levels[2:])
        result = Level10Engine().analyze(self.snapshot, *levels)

        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("level6_symbol_mismatch", result.warnings)
        self.assertFalse(result.metadata["input_validation_passed"])
        self.assertIn("invalid_level10_input", result.weaknesses)

    def test_rejects_nan_in_score(self):
        bad_level5 = replace(self.levels[0], score=math.nan)
        levels = (bad_level5, *self.levels[1:])
        result = Level10Engine().analyze(self.snapshot, *levels)

        self.assertEqual(result.score, 0.0)
        self.assertIn("level5_score_invalid", result.warnings)
        self.assertFalse(result.metadata["input_validation_passed"])

    def test_rejects_infinite_and_out_of_range_analyzer_fields(self):
        bad_level6 = replace(self.levels[1], risk_reward=math.inf)
        bad_level9 = replace(self.levels[4], opportunity_priority=1.1)
        levels = (self.levels[0], bad_level6, self.levels[2], self.levels[3], bad_level9)
        result = Level10Engine().analyze(self.snapshot, *levels)

        self.assertIn("level6_risk_reward_invalid", result.warnings)
        self.assertIn("level9_opportunity_priority_invalid", result.warnings)
        self.assertEqual(result.confidence, 0.0)

    def test_rejects_non_numeric_confidence(self):
        bad_level7 = replace(self.levels[2], confidence="0.8")
        levels = (self.levels[0], self.levels[1], bad_level7, *self.levels[3:])
        result = Level10Engine().analyze(self.snapshot, *levels)

        self.assertIn("level7_confidence_invalid", result.warnings)
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.confidence, 0.0)

    def test_rejects_malformed_warning_collection(self):
        bad_level8 = replace(self.levels[3], warnings=None)
        levels = (*self.levels[:3], bad_level8, self.levels[4])
        result = Level10Engine().analyze(self.snapshot, *levels)

        self.assertIn("level8_warnings_invalid", result.warnings)
        self.assertEqual(result.score, 0.0)


if __name__ == "__main__":
    unittest.main()
