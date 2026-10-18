from __future__ import annotations

import unittest
from types import SimpleNamespace

from bot.main import _evaluate_decisions


class DecisionEngineMainWiringTests(unittest.TestCase):
    def test_aggregate_intelligence_reaches_decision_engine(self):
        intelligence = SimpleNamespace(
            overall_score=0.82,
            overall_confidence=0.77,
            overall_consistency=0.73,
        )

        decisions = _evaluate_decisions({"SBER": intelligence}, SimpleNamespace(positions={}))

        self.assertEqual(set(decisions), {"SBER"})
        self.assertEqual(decisions["SBER"].ticker, "SBER")
        self.assertEqual(decisions["SBER"].action, "BUY")
        self.assertAlmostEqual(decisions["SBER"].score, 0.82)

    def test_held_ticker_is_evaluated_as_held_not_new_buy(self):
        intelligence = SimpleNamespace(
            overall_score=0.82,
            overall_confidence=0.77,
            overall_consistency=0.73,
        )
        portfolio = SimpleNamespace(positions={"SBER": object()})

        decisions = _evaluate_decisions({"SBER": intelligence}, portfolio)

        self.assertEqual(decisions["SBER"].action, "HOLD")


if __name__ == "__main__":
    unittest.main()
