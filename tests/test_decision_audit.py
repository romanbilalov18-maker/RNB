import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from bot.decision_audit import DecisionAuditStore


class DecisionAuditStoreTests(unittest.TestCase):
    def test_records_recommendations_and_virtual_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            decisions = {
                "AAA": SimpleNamespace(
                    action="BUY", reason="strong signal",
                    score=0.8, confidence=0.7, consistency=0.9,
                ),
                "BBB": SimpleNamespace(
                    action="WAIT", reason="low confidence",
                    score=0.3, confidence=0.2, consistency=0.8,
                ),
            }
            trades = [
                SimpleNamespace(
                    ticker="AAA", side="BUY", quantity=2,
                    commission=1.5, realized_pnl=0.0,
                )
            ]
            count = store.record_cycle(
                "cycle-1", decisions, trades,
                equity=9990.0, cash=5000.0, total_commissions=1.5,
            )
            self.assertEqual(count, 2)
            summary = store.summary()
            self.assertEqual(summary["observations"], 2)
            self.assertEqual(summary["cycles"], 1)
            self.assertEqual(summary["observations_with_trades"], 1)
            self.assertAlmostEqual(summary["recorded_trade_commissions"], 1.5)

    def test_idempotent_for_same_cycle_and_ticker(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            decision = {"AAA": SimpleNamespace(action="WAIT", reason="wait")}
            kwargs = dict(
                cycle_id="cycle-1", decisions=decision, virtual_trades=[],
                equity=1000.0, cash=1000.0, total_commissions=0.0,
            )
            store.record_cycle(**kwargs)
            store.record_cycle(**kwargs)
            self.assertEqual(store.summary()["observations"], 1)

    def test_trade_without_recommendation_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            trade = SimpleNamespace(
                ticker="XYZ", side="BUY", quantity=1,
                commission=0.5, realized_pnl=0.0,
            )
            store.record_cycle(
                "cycle-1", {}, [trade],
                equity=990.0, cash=500.0, total_commissions=0.5,
            )
            self.assertEqual(store.summary()["observations"], 1)
            self.assertEqual(store.summary()["observations_with_trades"], 1)


if __name__ == "__main__":
    unittest.main()
