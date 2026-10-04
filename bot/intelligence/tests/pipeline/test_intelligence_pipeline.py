import unittest
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.pipeline.intelligence_pipeline import IntelligencePipeline
from bot.intelligence.pipeline.intelligence_result import IntelligenceResult

class IntelligencePipelineTests(unittest.TestCase):
    def setUp(self):
        self.pipeline=IntelligencePipeline()
        self.snapshot=MarketSnapshot("TEST",105.0,100.0,1500.0,1000.0,0.02,0.04,0.85)

    def test_runs_all_fifteen_levels(self):
        result=self.pipeline.analyze(self.snapshot)
        self.assertIsInstance(result,IntelligenceResult)
        self.assertEqual(result.metadata["levels"],15)
        for level in range(1,16):
            self.assertEqual(getattr(result,f"level_{level:02d}").symbol,"TEST")

    def test_level_15_is_master_output(self):
        result=self.pipeline.analyze(self.snapshot)
        self.assertAlmostEqual(result.overall_score,result.level_15.score)
        self.assertAlmostEqual(result.overall_confidence,result.level_15.confidence)
        self.assertAlmostEqual(result.overall_consistency,result.level_15.consistency)
        self.assertTrue(result.level_15.metadata["master_synthesis"])
        self.assertFalse(result.level_15.metadata["trade_decision"])

    def test_levels_are_bounded(self):
        result=self.pipeline.analyze(self.snapshot)
        values=(result.overall_score,result.overall_confidence,result.overall_consistency,*(getattr(result,f"level_{i:02d}").score for i in range(1,16)))
        for value in values:
            self.assertGreaterEqual(value,0.0); self.assertLessEqual(value,1.0)

    def test_pipeline_passes_learning_history(self):
        from bot.intelligence.levels.level_11.models.learning_observation import LearningObservation
        obs=(LearningObservation(0.03,True,{"level_10":0.8},{"momentum":0.75},"trend"),)
        result=IntelligencePipeline(obs).analyze(self.snapshot)
        self.assertEqual(result.level_11.sample_count,1); self.assertGreater(result.level_11.learning_confidence,0.0)

    def test_pipeline_runs_anomaly_detection(self):
        result=self.pipeline.analyze(self.snapshot); self.assertEqual(len(result.level_12.analyzer_results),6)

    def test_pipeline_runs_scenario_forecasting(self):
        result=self.pipeline.analyze(self.snapshot); self.assertEqual(len(result.level_13.analyzer_results),6); self.assertTrue(0<=result.level_13.scenario_confidence<=1)

    def test_pipeline_runs_adversarial_analysis(self):
        result=self.pipeline.analyze(self.snapshot); self.assertEqual(len(result.level_14.analyzer_results),6)

    def test_pipeline_runs_master_intelligence(self):
        result=self.pipeline.analyze(self.snapshot); self.assertEqual(len(result.level_15.analyzer_results),7)

    def test_no_trade_decision_is_created(self):
        result=self.pipeline.analyze(self.snapshot)
        self.assertFalse(hasattr(result,"buy")); self.assertFalse(hasattr(result,"sell")); self.assertFalse(hasattr(result,"action"))

if __name__=="__main__":
    unittest.main()
