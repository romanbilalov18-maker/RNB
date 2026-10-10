import math
import unittest
from types import SimpleNamespace

from bot.intelligence.decision_engine import DecisionEngine


def result(score=0.7, confidence=0.8, consistency=0.75):
    return SimpleNamespace(
        overall_score=score,
        overall_confidence=confidence,
        overall_consistency=consistency,
    )


class DecisionEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = DecisionEngine()

    def test_buy_when_all_candidate_thresholds_pass(self):
        self.assertEqual(self.engine.decide("AAA", result()).action, "BUY")

    def test_wait_when_score_is_below_threshold(self):
        self.assertEqual(self.engine.decide("AAA", result(score=0.59)).action, "WAIT")

    def test_wait_when_confidence_is_low(self):
        self.assertEqual(self.engine.decide("AAA", result(confidence=0.49)).action, "WAIT")

    def test_wait_when_consistency_is_low(self):
        self.assertEqual(self.engine.decide("AAA", result(consistency=0.49)).action, "WAIT")

    def test_missing_result_never_buys(self):
        self.assertEqual(self.engine.decide("AAA", None).action, "WAIT")

    def test_malformed_result_never_buys(self):
        self.assertEqual(self.engine.decide("AAA", object()).action, "WAIT")

    def test_non_finite_metrics_never_buy(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                self.assertEqual(self.engine.decide("AAA", result(score=value)).action, "WAIT")

    def test_out_of_range_metrics_never_buy(self):
        self.assertEqual(self.engine.decide("AAA", result(score=1.1)).action, "WAIT")

    def test_weak_held_position_gets_sell_recommendation_only(self):
        decision = self.engine.decide("AAA", result(score=0.2, confidence=0.7), is_held=True)
        self.assertEqual(decision.action, "SELL")
        self.assertIn("PositionManager", decision.reason)

    def test_held_position_defaults_to_hold(self):
        self.assertEqual(self.engine.decide("AAA", result(score=0.5), is_held=True).action, "HOLD")

    def test_evaluate_uses_held_ticker_context(self):
        decisions = self.engine.evaluate(
            {"AAA": result(score=0.2, confidence=0.7), "BBB": result()},
            held_tickers={"AAA"},
        )
        self.assertEqual(decisions["AAA"].action, "SELL")
        self.assertEqual(decisions["BBB"].action, "BUY")

    def test_invalid_threshold_rejected(self):
        with self.assertRaises(ValueError):
            DecisionEngine(min_buy_score=1.1)

    def test_non_finite_threshold_rejected(self):
        with self.assertRaises(ValueError):
            DecisionEngine(min_buy_score=math.nan)

    def test_sell_threshold_must_be_below_buy_threshold(self):
        with self.assertRaises(ValueError):
            DecisionEngine(min_buy_score=0.3, max_sell_score=0.3)


if __name__ == "__main__":
    unittest.main()
