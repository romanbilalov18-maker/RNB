import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from bot.decision_audit import DecisionAuditStore

def candle(day, close):
    return SimpleNamespace(time=datetime.fromisoformat(day).replace(tzinfo=timezone.utc), close=close)

class DecisionAuditStoreTests(unittest.TestCase):
    def test_records_recommendations_and_virtual_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            decisions = {
                "AAA": SimpleNamespace(action="BUY", reason="strong signal", score=.8, confidence=.7, consistency=.9),
                "BBB": SimpleNamespace(action="WAIT", reason="low confidence", score=.3, confidence=.2, consistency=.8),
            }
            trade = SimpleNamespace(ticker="AAA", side="BUY", quantity=2, commission=1.5, realized_pnl=0.0)
            count = store.record_cycle("cycle-1", decisions, [trade], equity=9990, cash=5000,
                total_commissions=1.5, current_prices={"AAA": 100}, candle_history={"AAA": [candle("2026-10-01", 99)]})
            self.assertEqual(count, 2)
            summary = store.summary()
            self.assertEqual(summary["observations"], 2)
            self.assertEqual(summary["cycles"], 1)
            self.assertEqual(summary["observations_with_trades"], 1)
            self.assertAlmostEqual(summary["recorded_trade_commissions"], 1.5)

    def test_idempotent_for_same_cycle_and_ticker(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            args = dict(cycle_id="cycle-1", decisions={"AAA": SimpleNamespace(action="WAIT", reason="wait")},
                virtual_trades=[], equity=1000, cash=1000, total_commissions=0)
            store.record_cycle(**args)
            store.record_cycle(**args)
            self.assertEqual(store.summary()["observations"], 1)

    def test_trade_without_recommendation_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            trade = SimpleNamespace(ticker="XYZ", side="BUY", quantity=1, commission=.5, realized_pnl=0)
            store.record_cycle("cycle-1", {}, [trade], equity=990, cash=500, total_commissions=.5)
            self.assertEqual(store.summary()["observations"], 1)
            self.assertEqual(store.summary()["observations_with_trades"], 1)

    def test_evaluates_buy_after_one_three_and_five_sessions_net_of_costs(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            decision = {"AAA": SimpleNamespace(action="BUY", reason="test", score=.8, confidence=.8, consistency=.8)}
            history = [candle("2026-10-01", 100)]
            store.record_cycle("anchor", decision, [], equity=1000, cash=1000, total_commissions=0,
                current_prices={"AAA": 100}, candle_history={"AAA": history}, commission_rate=.001)
            future = [candle("2026-10-02", 101), candle("2026-10-05", 102),
                candle("2026-10-06", 99), candle("2026-10-07", 103), candle("2026-10-08", 104)]
            store.record_cycle("later", {}, [], equity=1000, cash=1000, total_commissions=0,
                candle_history={"AAA": history + future}, commission_rate=.001)
            with store._connect() as db:
                outcomes = db.execute("SELECT horizon_sessions, target_price, direction_correct FROM decision_outcomes ORDER BY horizon_sessions").fetchall()
            self.assertEqual([r["horizon_sessions"] for r in outcomes], [1, 3, 5])
            self.assertEqual([r["target_price"] for r in outcomes], [101, 99, 104])
            self.assertEqual([r["direction_correct"] for r in outcomes], [1, 0, 1])

if __name__ == "__main__":
    unittest.main()
