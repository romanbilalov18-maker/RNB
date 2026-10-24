from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace

from bot.intelligence.decision_engine import DecisionEngine
from bot.main import _evaluate_decisions, _print_decision_diagnostics


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


    def test_cycle_diagnostics_report_thresholds_actions_and_reasons(self):
        engine = DecisionEngine()
        decisions = {
            "AAA": engine.decide("AAA", SimpleNamespace(
                overall_score=0.82,
                overall_confidence=0.77,
                overall_consistency=0.73,
            )),
            "BBB": engine.decide("BBB", SimpleNamespace(
                overall_score=0.2,
                overall_confidence=0.4,
                overall_consistency=0.3,
            )),
        }
        output = StringIO()
        with redirect_stdout(output):
            _print_decision_diagnostics(decisions, engine)

        log = output.getvalue()
        self.assertIn("BUY score>=0.60", log)
        self.assertIn("confidence>=0.50", log)
        self.assertIn("DECISION SUMMARY: total=2 BUY=1 WAIT=1", log)
        self.assertIn("пройдены пороги оценки", log)
        self.assertIn("недостаточная уверенность", log)


if __name__ == "__main__":
    unittest.main()
