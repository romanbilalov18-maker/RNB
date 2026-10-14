from types import SimpleNamespace
import unittest

from bot.intelligence.levels.level_15.level_15_engine import Level15Engine


def inputs(*, learning_confidence=0.0):
    l6 = SimpleNamespace(risk_reward=0.7, risk_consistency=0.7, confidence=0.8)
    l10 = SimpleNamespace(
        symbol="TEST",
        conviction=0.7,
        cross_level_agreement=0.7,
        confidence_quality=0.8,
        risk_adjusted_conviction=0.7,
        confidence=0.8,
    )
    l11 = SimpleNamespace(
        outcome_quality=0.0,
        level_effectiveness=0.0,
        analyzer_effectiveness=0.0,
        learning_confidence=0.0,
        confidence=learning_confidence,
    )
    l12 = SimpleNamespace(score=0.2, confidence=0.8)
    l13 = SimpleNamespace(
        scenario_confidence=0.7,
        neutral_scenario=0.7,
        adverse_scenario=0.2,
        confidence=0.8,
    )
    l14 = SimpleNamespace(score=0.2, data_reliability=0.8, confidence=0.8)
    return l6, l10, l11, l12, l13, l14


class Level15MissingEvidenceTests(unittest.TestCase):
    def test_missing_learning_history_does_not_dilute_master_score(self):
        engine = Level15Engine()
        without_learning = engine.analyze(*inputs(learning_confidence=0.0))
        with_learning = engine.analyze(*inputs(learning_confidence=0.8))

        self.assertGreater(without_learning.score, 0.55)
        self.assertGreater(without_learning.confidence, 0.5)
        self.assertIn("learning_quality", without_learning.metadata["excluded_unavailable_analyzers"])
        self.assertGreater(with_learning.score, 0.0)

    def test_final_consistency_uses_cross_level_agreement(self):
        result = Level15Engine().analyze(*inputs())
        self.assertAlmostEqual(result.consistency, 0.7)
        self.assertEqual(result.metadata["consistency_source"], "L10.cross_level_agreement")

    def test_missing_agreement_confidence_does_not_claim_consistency(self):
        l6, l10, l11, l12, l13, l14 = inputs()
        l10.confidence = 0.0
        result = Level15Engine().analyze(l6, l10, l11, l12, l13, l14)
        self.assertEqual(result.consistency, 0.0)
        self.assertEqual(result.confidence, 0.0)

    def test_all_missing_evidence_returns_zero_confidence(self):
        l6, l10, l11, l12, l13, l14 = inputs()
        for item in (l6, l10, l12, l13, l14):
            item.confidence = 0.0
        result = Level15Engine().analyze(l6, l10, l11, l12, l13, l14)
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.score, 0.0)


if __name__ == "__main__":
    unittest.main()
