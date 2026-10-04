import unittest

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.pipeline.intelligence_pipeline import IntelligencePipeline
from bot.intelligence.pipeline.intelligence_result import IntelligenceResult


class IntelligencePipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = IntelligencePipeline()
        self.snapshot = MarketSnapshot("TEST", 105.0, 100.0, 1500.0, 1000.0, 0.02, 0.04, 0.85)

    def test_runs_all_eleven_levels(self) -> None:
        result = self.pipeline.analyze(self.snapshot)
        self.assertIsInstance(result, IntelligenceResult)
        self.assertEqual(result.symbol, "TEST")
        self.assertEqual(result.metadata["levels"], 11)
        for level in range(1, 12):
            self.assertEqual(getattr(result, f"level_{level:02d}").symbol, "TEST")

    def test_levels_are_bounded(self) -> None:
        result = self.pipeline.analyze(self.snapshot)
        values = (
            result.overall_score, result.overall_confidence, result.overall_consistency,
            result.level_01.score, result.level_02.score, result.level_03.score,
            result.level_04.score, result.level_05.score, result.level_06.score,
            result.level_07.score, result.level_08.score, result.level_09.score,
            result.level_10.score, result.level_11.score,
        )
        for value in values:
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_pipeline_preserves_level_ten_output(self) -> None:
        result = self.pipeline.analyze(self.snapshot)
        self.assertEqual(result.overall_score, result.level_10.score)
        self.assertEqual(result.overall_confidence, result.level_10.confidence)
        self.assertEqual(result.overall_consistency, result.level_10.consistency)

    def test_pipeline_passes_learning_history(self) -> None:
        from bot.intelligence.levels.level_11.models.learning_observation import LearningObservation
        observations = (LearningObservation(0.03, True, {"level_10": 0.8}, {"momentum": 0.75}, "trend"),)
        result = IntelligencePipeline(observations).analyze(self.snapshot)
        self.assertEqual(result.level_11.sample_count, 1)
        self.assertGreater(result.level_11.learning_confidence, 0.0)

    def test_no_trade_decision_is_created(self) -> None:
        result = self.pipeline.analyze(self.snapshot)
        self.assertFalse(hasattr(result, "buy"))
        self.assertFalse(hasattr(result, "sell"))
        self.assertFalse(hasattr(result, "action"))


if __name__ == "__main__":
    unittest.main()
