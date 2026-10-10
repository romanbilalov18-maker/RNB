import unittest
from types import SimpleNamespace

from bot.main import _evaluate_decisions


class DecisionEngineCycleIntegrationTests(unittest.TestCase):
    def test_cycle_evaluates_held_and_candidate_tickers(self):
        intelligence_results = {
            "HELD": SimpleNamespace(
                overall_score=0.2,
                overall_confidence=0.7,
                overall_consistency=0.8,
            ),
            "CANDIDATE": SimpleNamespace(
                overall_score=0.75,
                overall_confidence=0.8,
                overall_consistency=0.7,
            ),
        }
        portfolio = SimpleNamespace(positions={"HELD": object()})

        decisions = _evaluate_decisions(intelligence_results, portfolio)

        self.assertEqual(decisions["HELD"].action, "SELL")
        self.assertEqual(decisions["CANDIDATE"].action, "BUY")

    def test_empty_intelligence_results_produce_no_decisions(self):
        portfolio = SimpleNamespace(positions={})
        self.assertEqual(_evaluate_decisions({}, portfolio), {})

    def test_invalid_intelligence_metrics_produce_wait(self):
        intelligence_results = {
            "BAD": SimpleNamespace(
                overall_score=float("nan"),
                overall_confidence=0.9,
                overall_consistency=0.9,
            )
        }
        portfolio = SimpleNamespace(positions={})
        decisions = _evaluate_decisions(intelligence_results, portfolio)
        self.assertEqual(decisions["BAD"].action, "WAIT")


if __name__ == "__main__":
    unittest.main()
