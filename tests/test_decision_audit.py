import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from bot.decision_audit import DecisionAuditStore


def candle(day, close):
    return SimpleNamespace(time=datetime.fromisoformat(day).replace(tzinfo=timezone.utc), close=close)


def intelligence_snapshot():
    levels = {}
    for number in range(1, 16):
        levels[f"level_{number:02d}"] = SimpleNamespace(
            score=number / 20,
            analyzer_results=(
                SimpleNamespace(analyzer="sample", score=number / 20),
            ) if number == 1 else (),
            metadata={"regime": "bullish"} if number == 3 else {},
        )
    return SimpleNamespace(**levels)


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
                current_prices={"AAA": 120}, candle_history={"AAA": history}, commission_rate=.001)
            self.assertEqual(store.pending_tickers(), {"AAA"})
            with store._connect() as db:
                anchor = db.execute("SELECT anchor_price, anchor_session_date FROM decision_audit").fetchone()
            self.assertEqual(anchor["anchor_price"], 100)
            self.assertEqual(anchor["anchor_session_date"], "2026-10-01")
            future = [candle("2026-10-02", 101), candle("2026-10-05", 102),
                candle("2026-10-06", 99), candle("2026-10-07", 103), candle("2026-10-08", 104)]
            store.record_cycle("later", {}, [], equity=1000, cash=1000, total_commissions=0,
                candle_history={"AAA": history + future}, commission_rate=.001)
            with store._connect() as db:
                outcomes = db.execute("SELECT horizon_sessions, target_price, direction_correct FROM decision_outcomes ORDER BY horizon_sessions").fetchall()
            self.assertEqual([r["horizon_sessions"] for r in outcomes], [1, 3, 5])
            self.assertEqual([r["target_price"] for r in outcomes], [101, 99, 104])
            self.assertEqual([r["direction_correct"] for r in outcomes], [1, 0, 1])
            self.assertEqual(store.pending_tickers(), set())

    def test_ignores_incomplete_current_daily_candle(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            today = datetime.now(timezone.utc).date().isoformat()
            yesterday = (datetime.now(timezone.utc).date() - __import__("datetime").timedelta(days=1)).isoformat()
            history = [candle(yesterday, 100), candle(today, 999)]
            store.record_cycle(
                "cycle-current",
                {"AAA": SimpleNamespace(action="BUY", reason="test")},
                [],
                equity=1000,
                cash=1000,
                total_commissions=0,
                candle_history={"AAA": history},
            )
            with store._connect() as db:
                anchor = db.execute(
                    "SELECT anchor_price, anchor_session_date FROM decision_audit"
                ).fetchone()
                prices = db.execute(
                    "SELECT session_date, close_price FROM market_session_prices ORDER BY session_date"
                ).fetchall()
            self.assertEqual(anchor["anchor_price"], 100)
            self.assertEqual(anchor["anchor_session_date"], yesterday)
            self.assertEqual([(row["session_date"], row["close_price"]) for row in prices], [(yesterday, 100)])

    def test_wait_outcomes_are_not_counted_as_directional_predictions(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            base = datetime.now(timezone.utc).date()
            days = [
                candle((base - __import__("datetime").timedelta(days=7-i)).isoformat(), 100+i)
                for i in range(7)
            ]
            store.record_cycle(
                "wait-anchor",
                {"AAA": SimpleNamespace(action="WAIT", reason="no signal")},
                [],
                equity=1000,
                cash=1000,
                total_commissions=0,
                candle_history={"AAA": days[:1]},
            )
            store.record_cycle(
                "wait-followup",
                {},
                [],
                equity=1000,
                cash=1000,
                total_commissions=0,
                candle_history={"AAA": days},
            )
            summary = store.summary()
            self.assertEqual([row["horizon_sessions"] for row in summary["forward_outcomes"]], [1, 3, 5])
            self.assertTrue(all(row["scored"] == 0 for row in summary["forward_outcomes"]))

    def test_matured_three_session_outcome_becomes_l11_learning_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            history = [candle("2026-10-01", 100)]
            store.record_cycle(
                "learning-anchor",
                {"AAA": SimpleNamespace(action="BUY", reason="test", score=.8, confidence=.8, consistency=.8)},
                [],
                equity=1000,
                cash=1000,
                total_commissions=0,
                candle_history={"AAA": history},
                intelligence_results={"AAA": intelligence_snapshot()},
                commission_rate=.001,
            )
            self.assertEqual(store.learning_observations_by_ticker(), {})
            future = [
                candle("2026-10-02", 101),
                candle("2026-10-05", 102),
                candle("2026-10-06", 103),
            ]
            store.record_cycle(
                "learning-followup",
                {},
                [],
                equity=1000,
                cash=1000,
                total_commissions=0,
                candle_history={"AAA": history + future},
                commission_rate=.001,
            )
            observations = store.learning_observations_by_ticker()["AAA"]
            self.assertEqual(len(observations), 1)
            self.assertTrue(observations[0].correct)
            self.assertGreater(observations[0].outcome_return, 0)
            self.assertEqual(observations[0].level_scores["L01"], .05)
            self.assertEqual(observations[0].level_scores["L15"], .75)
            self.assertEqual(observations[0].analyzer_scores["L01:sample"], .05)
            self.assertEqual(observations[0].regime, "bullish")

    def test_learning_history_ignores_waits_and_is_capped_per_ticker(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            self.assertEqual(store.learning_observations_by_ticker(), {})
            self.assertEqual(store.summary()["learning_observations"], 0)


if __name__ == "__main__":
    unittest.main()
