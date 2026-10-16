import unittest
from types import SimpleNamespace

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.level_01_engine import Level1Engine
from bot.intelligence.levels.level_02.level_02_engine import Level2Engine
from bot.intelligence.levels.level_03.level_03_engine import Level3Engine
from bot.intelligence.levels.level_04.level_04_engine import Level4Engine
from bot.intelligence.levels.level_05.level_05_engine import Level5Engine
from bot.intelligence.levels.level_06.level_06_engine import Level6Engine
from bot.intelligence.levels.level_07.level_07_engine import Level7Engine
from bot.intelligence.levels.level_08.level_08_engine import Level8Engine
from bot.intelligence.levels.level_09.level_09_engine import Level9Engine
from bot.intelligence.levels.level_09.analyzers.diversification_value import analyze as analyze_diversification
from bot.intelligence.levels.level_09.analyzers.correlation_risk import analyze as analyze_correlation


class TestLevel9(unittest.TestCase):
    def setUp(self):
        s = MarketSnapshot("TEST", 105.0, 100.0, 1500.0, 1000.0, 0.02, 0.03, 0.8)
        l1 = Level1Engine().analyze(s); l2 = Level2Engine().analyze(s, l1); l3 = Level3Engine().analyze(s, l2)
        l4 = Level4Engine().analyze(s, l3); l5 = Level5Engine().analyze(s, l2, l3, l4); l6 = Level6Engine().analyze(s, l5)
        l7 = Level7Engine().analyze(s, l3, l4, l5, l6); l8 = Level8Engine().analyze(s, l3, l4, l7)
        self.snapshot, self.l5, self.l6, self.l8 = s, l5, l6, l8

    def test_all_six_analyzers_run(self):
        result = Level9Engine().analyze(self.snapshot, self.l5, self.l6, self.l8)
        self.assertEqual(len(result.analyzer_results), 6)
        self.assertTrue(0.0 <= result.score <= 1.0)
        self.assertTrue(0.0 <= result.confidence <= 1.0)

    def test_portfolio_scores_are_bounded(self):
        result = Level9Engine().analyze(self.snapshot, self.l5, self.l6, self.l8)
        for value in (result.concentration_risk, result.diversification_value, result.portfolio_compatibility, result.correlation_risk, result.opportunity_priority, result.portfolio_consistency):
            self.assertTrue(0.0 <= value <= 1.0)

    def test_missing_portfolio_context_is_explicit_and_not_high_confidence(self):
        result = Level9Engine().analyze(self.snapshot, self.l5, self.l6, self.l8)
        self.assertIn("portfolio_positions_not_available", result.warnings)
        self.assertIn("existing_positions_not_available", result.warnings)
        self.assertLess(result.confidence, 0.8)

    def test_known_empty_portfolio_does_not_claim_diversification(self):
        snapshot = MarketSnapshot("TEST", 105.0, 100.0, portfolio_context_available=True)
        result = analyze_diversification(snapshot, self.l8)
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("portfolio_diversification_not_applicable", result.warnings)

    def test_diversification_uses_exposure_weights_not_just_sector_count(self):
        snapshot = SimpleNamespace(
            portfolio_positions=(
                {"market_value": 90.0, "market_value_available": True, "sector": "A"},
                {"market_value": 10.0, "market_value_available": True, "sector": "B"},
            ),
            portfolio_context_available=True,
        )
        result = analyze_diversification(snapshot, None)
        self.assertAlmostEqual(result.metrics["sector_hhi"], 0.82)
        self.assertGreater(result.score, 0.0)
        self.assertLess(result.score, 0.5)

    def test_correlation_rejects_misaligned_date_return_arrays(self):
        snapshot = SimpleNamespace(
            symbol="TEST",
            portfolio_positions=({"symbol":"OTHER","market_value":100.0,"historical_return_dates":["1","2"],"historical_returns":[0.1]},),
            historical_return_dates=tuple(str(i) for i in range(12)),
            historical_returns=tuple(i / 100 for i in range(12)),
            portfolio_context_available=True,
        )
        result = analyze_correlation(snapshot, None, None)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("portfolio_correlation_history_insufficient", result.warnings)
        self.assertIn("portfolio_return_dates_values_misaligned", result.warnings)

    def test_cross_level_symbol_mismatch_suppresses_aggregate(self):
        wrong_l8 = SimpleNamespace(symbol="OTHER", score=0.8, confidence=0.9, risk_reward=0.7)
        result = Level9Engine().analyze(self.snapshot, self.l5, self.l6, wrong_l8)
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("level8_symbol_mismatch", result.warnings)

    def test_does_not_mutate_inputs(self):
        before = (self.l5, self.l6, self.l8)
        Level9Engine().analyze(self.snapshot, *before)
        self.assertEqual(before, (self.l5, self.l6, self.l8))


if __name__ == "__main__":
    unittest.main()
