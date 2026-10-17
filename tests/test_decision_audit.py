import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
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

    def test_closed_virtual_trade_is_attached_separately_from_forecast_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            trade = SimpleNamespace(
                ticker="AAA", side="SELL", quantity=2, commission=1.0,
                realized_pnl=18.0, entry_price=100.0, price=110.0,
            )
            store.record_cycle(
                "closed-trade",
                {"AAA": SimpleNamespace(action="SELL", reason="exit signal")},
                [trade],
                equity=1018, cash=1018, total_commissions=1.0,
                current_prices={"AAA": 110},
                candle_history={"AAA": [candle("2026-10-01", 100)]},
                intelligence_results={"AAA": intelligence_snapshot()},
                as_of=datetime.fromisoformat("2026-10-02T12:00:00+00:00"),
            )
            future = [candle("2026-10-05", 111), candle("2026-10-06", 112),
                      candle("2026-10-07", 113)]
            store.record_cycle(
                "maturity",
                {}, [],
                equity=1018, cash=1018, total_commissions=1.0,
                candle_history={"AAA": [candle("2026-10-01", 100)] + future},
                as_of=datetime.fromisoformat("2026-10-08T12:00:00+00:00"),
            )
            observation = store.learning_observations_by_ticker()["AAA"][0]
            self.assertAlmostEqual(observation.realized_trade_return, 0.09)
            self.assertTrue(observation.correct)
            self.assertAlmostEqual(observation.outcome_return, (113 / 100 - 1) - .001)


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
            as_of = datetime.fromisoformat("2026-10-02T12:00:00+00:00")
            history = [candle("2026-10-01", 100)]
            store.record_cycle("anchor", decision, [], equity=1000, cash=1000, total_commissions=0,
                current_prices={"AAA": 100}, candle_history={"AAA": history}, commission_rate=.001, as_of=as_of)
            self.assertEqual(store.pending_tickers(), {"AAA"})
            with store._connect() as db:
                anchor = db.execute("SELECT anchor_price, anchor_session_date FROM decision_audit").fetchone()
            self.assertEqual(anchor["anchor_price"], 100)
            self.assertEqual(anchor["anchor_session_date"], "2026-10-02")
            future = [candle("2026-10-05", 101), candle("2026-10-06", 102),
                candle("2026-10-07", 99), candle("2026-10-08", 103), candle("2026-10-09", 104)]
            store.record_cycle("later", {}, [], equity=1000, cash=1000, total_commissions=0,
                candle_history={"AAA": history + future}, commission_rate=.001,
                as_of=datetime.fromisoformat("2026-10-10T12:00:00+00:00"))
            with store._connect() as db:
                outcomes = db.execute("SELECT horizon_sessions, target_price, direction_correct FROM decision_outcomes ORDER BY horizon_sessions").fetchall()
            self.assertEqual([r["horizon_sessions"] for r in outcomes], [1, 3, 5])
            self.assertEqual([r["target_price"] for r in outcomes], [101, 99, 104])
            self.assertEqual([r["direction_correct"] for r in outcomes], [1, 0, 1])
            self.assertEqual(store.pending_tickers(), set())

    def test_uses_decision_time_price_and_excludes_same_day_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            as_of = datetime.now(timezone.utc)
            today = as_of.astimezone(DecisionAuditStore.MARKET_TIMEZONE).date().isoformat()
            yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
            history = [candle(yesterday, 100), candle(today, 999)]
            store.record_cycle(
                "cycle-current",
                {"AAA": SimpleNamespace(action="BUY", reason="test")},
                [],
                equity=1000,
                cash=1000,
                total_commissions=0,
                current_prices={"AAA": 105},
                candle_history={"AAA": history},
                as_of=as_of,
            )
            with store._connect() as db:
                anchor = db.execute(
                    "SELECT anchor_price, anchor_session_date FROM decision_audit"
                ).fetchone()
                prices = db.execute(
                    "SELECT session_date, close_price FROM market_session_prices ORDER BY session_date"
                ).fetchall()
            self.assertEqual(anchor["anchor_price"], 105)
            self.assertEqual(anchor["anchor_session_date"], today)
            self.assertEqual([(row["session_date"], row["close_price"]) for row in prices], [(yesterday, 100)])

    def test_wait_outcomes_are_not_counted_as_directional_predictions(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            base = datetime.now(timezone.utc).date()
            as_of = datetime.combine(base, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=12)
            prior = [
                candle((base - timedelta(days=7-i)).isoformat(), 100+i)
                for i in range(7)
            ]
            store.record_cycle(
                "wait-anchor",
                {"AAA": SimpleNamespace(action="WAIT", reason="no signal")},
                [],
                equity=1000,
                cash=1000,
                total_commissions=0,
                current_prices={"AAA": 100},
                candle_history={"AAA": prior},
                as_of=as_of,
            )
            future = [
                candle((base + timedelta(days=i)).isoformat(), 100+i)
                for i in range(1, 8)
            ]
            store.record_cycle(
                "wait-followup",
                {},
                [],
                equity=1000,
                cash=1000,
                total_commissions=0,
                candle_history={"AAA": prior + future},
                as_of=as_of + timedelta(days=10),
            )
            summary = store.summary()
            self.assertEqual([row["horizon_sessions"] for row in summary["forward_outcomes"]], [1, 3, 5])
            self.assertTrue(all(row["scored"] == 0 for row in summary["forward_outcomes"]))

    def test_matured_three_session_outcome_becomes_l11_learning_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            as_of = datetime.fromisoformat("2026-10-02T12:00:00+00:00")
            history = [candle("2026-10-01", 100)]
            store.record_cycle(
                "learning-anchor",
                {"AAA": SimpleNamespace(action="BUY", reason="test", score=.8, confidence=.8, consistency=.8)},
                [],
                equity=1000,
                cash=1000,
                total_commissions=0,
                current_prices={"AAA": 100},
                candle_history={"AAA": history},
                intelligence_results={"AAA": intelligence_snapshot()},
                commission_rate=.001,
                as_of=as_of,
            )
            self.assertEqual(store.learning_observations_by_ticker(), {})
            future = [
                candle("2026-10-05", 101),
                candle("2026-10-06", 102),
                candle("2026-10-07", 103),
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
                as_of=datetime.fromisoformat("2026-10-08T12:00:00+00:00"),
            )
            observations = store.learning_observations_by_ticker()["AAA"]
            self.assertEqual(len(observations), 1)
            self.assertTrue(observations[0].correct)
            self.assertGreater(observations[0].outcome_return, 0)
            self.assertEqual(observations[0].level_scores["L01"], .05)
            self.assertEqual(observations[0].level_scores["L15"], .75)
            self.assertEqual(observations[0].analyzer_scores["L01:sample"], .05)
            self.assertEqual(observations[0].regime, "bullish")

    def test_learning_observations_are_ordered_by_decision_time_not_maturity_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            first_as_of = datetime.fromisoformat("2026-10-02T12:00:00+00:00")
            second_as_of = datetime.fromisoformat("2026-10-03T12:00:00+00:00")
            first_history = [candle("2026-10-01", 100)]
            second_history = first_history + [candle("2026-10-02", 100)]
            for cycle_id, as_of, price, history in (
                ("older-decision", first_as_of, 100, first_history),
                ("newer-decision", second_as_of, 200, second_history),
            ):
                store.record_cycle(
                    cycle_id,
                    {"AAA": SimpleNamespace(action="BUY", reason="test")},
                    [],
                    equity=1000, cash=1000, total_commissions=0,
                    current_prices={"AAA": price},
                    candle_history={"AAA": history},
                    intelligence_results={"AAA": intelligence_snapshot()},
                    commission_rate=.001,
                    as_of=as_of,
                )

            future = [
                candle("2026-10-05", 101),
                candle("2026-10-06", 102),
                candle("2026-10-07", 103),
                candle("2026-10-08", 104),
            ]
            store.record_cycle(
                "maturity-cycle", {}, [], equity=1000, cash=1000, total_commissions=0,
                candle_history={"AAA": first_history + future},
                commission_rate=.001,
                as_of=datetime.fromisoformat("2026-10-10T12:00:00+00:00"),
            )
            # Simulate asynchronous maturity: the older decision's outcome is
            # processed later. Learning order must still follow decision time.
            with store._connect() as db:
                db.execute("""
                    UPDATE decision_outcomes
                    SET evaluated_at=CASE
                        WHEN audit_id=(SELECT id FROM decision_audit WHERE cycle_id='older-decision')
                        THEN '2026-10-12T00:00:00+00:00'
                        ELSE '2026-10-11T00:00:00+00:00'
                    END
                    WHERE horizon_sessions=3
                """)
                db.commit()

            observations = store.learning_observations_by_ticker()["AAA"]
            self.assertEqual(len(observations), 2)
            self.assertAlmostEqual(observations[0].outcome_return, .028)
            self.assertAlmostEqual(observations[1].outcome_return, (103 / 200 - 1) - .002)

    def test_summary_explains_learning_readiness_and_counts_only_trainable_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            as_of = datetime.fromisoformat("2026-10-02T12:00:00+00:00")
            store.record_cycle(
                "anchor",
                {"AAA": SimpleNamespace(action="BUY", reason="test", score=.8)},
                [],
                equity=1000, cash=1000, total_commissions=0,
                current_prices={"AAA": 100},
                candle_history={"AAA": [candle("2026-10-01", 100)]},
                intelligence_results={"AAA": intelligence_snapshot()},
                as_of=as_of,
            )
            summary = store.summary()
            self.assertEqual(summary["outcome_readiness"]["anchors"], 1)
            self.assertEqual(summary["outcome_readiness"]["anchored"], 1)
            self.assertEqual(summary["outcome_readiness"]["learning_snapshots"], 1)
            self.assertEqual(summary["learning_observations"], 0)
            self.assertEqual(summary["outcomes_ready_but_missing"], {"1": 0, "3": 0, "5": 0})
            self.assertEqual(
                [(row["horizon_sessions"], row["evaluated"], row["scored"])
                 for row in summary["forward_outcomes"]],
                [(1, 0, 0), (3, 0, 0), (5, 0, 0)],
            )
            self.assertEqual(summary["learning_pipeline"]["total_decisions"], 1)
            self.assertEqual(summary["learning_pipeline"]["missing_anchor"], 0)
            self.assertEqual(summary["learning_pipeline"]["non_directional"], 0)
            self.assertEqual(summary["learning_pipeline"]["missing_learning_snapshot"], 0)
            self.assertEqual(summary["learning_pipeline"]["awaiting_matured_outcome"], 1)
            self.assertEqual(summary["learning_pipeline"]["observations_after_deduplication"], 0)

    def test_pending_tickers_excludes_decisions_without_a_valid_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            store.record_cycle(
                "legacy",
                {
                    "NO_PRICE": SimpleNamespace(action="BUY", reason="missing live price"),
                    "ANCHORED": SimpleNamespace(action="BUY", reason="valid live price"),
                },
                [],
                equity=1000,
                cash=1000,
                total_commissions=0,
                current_prices={"ANCHORED": 100},
                as_of=datetime.fromisoformat("2026-10-02T12:00:00+00:00"),
            )
            self.assertEqual(store.pending_tickers(), {"ANCHORED"})

    def test_successful_sell_learning_return_is_positive_when_price_falls(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            as_of = datetime.fromisoformat("2026-10-02T12:00:00+00:00")
            history = [candle("2026-10-01", 100)]
            store.record_cycle(
                "sell-anchor",
                {"AAA": SimpleNamespace(action="SELL", reason="downside signal")},
                [],
                equity=1000, cash=1000, total_commissions=0,
                current_prices={"AAA": 100},
                candle_history={"AAA": history},
                intelligence_results={"AAA": intelligence_snapshot()},
                commission_rate=.001,
                as_of=as_of,
            )
            future = [
                candle("2026-10-05", 99),
                candle("2026-10-06", 98),
                candle("2026-10-07", 95),
            ]
            store.record_cycle(
                "sell-followup", {}, [], equity=1000, cash=1000,
                total_commissions=0, candle_history={"AAA": history + future},
                commission_rate=.001,
                as_of=datetime.fromisoformat("2026-10-08T12:00:00+00:00"),
            )
            observation = store.learning_observations_by_ticker()["AAA"][0]
            self.assertTrue(observation.correct)
            self.assertGreater(observation.outcome_return, 0)

    def test_learning_history_ignores_waits_and_is_capped_per_ticker(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            self.assertEqual(store.learning_observations_by_ticker(), {})
            self.assertEqual(store.summary()["learning_observations"], 0)


    def test_l11_learning_uses_only_latest_decision_per_ticker_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            as_of = datetime.fromisoformat("2026-10-02T12:00:00+00:00")
            history = [candle("2026-10-01", 100)]
            for cycle_id, price in (("early-cycle", 100), ("late-cycle", 200)):
                store.record_cycle(
                    cycle_id,
                    {"AAA": SimpleNamespace(action="BUY", reason="test")},
                    [],
                    equity=1000,
                    cash=1000,
                    total_commissions=0,
                    current_prices={"AAA": price},
                    candle_history={"AAA": history},
                    intelligence_results={"AAA": intelligence_snapshot()},
                    commission_rate=.001,
                    as_of=as_of,
                )

            future = [
                candle("2026-10-05", 101),
                candle("2026-10-06", 102),
                candle("2026-10-07", 103),
            ]
            store.record_cycle(
                "maturity-cycle",
                {},
                [],
                equity=1000,
                cash=1000,
                total_commissions=0,
                candle_history={"AAA": history + future},
                commission_rate=.001,
                as_of=datetime.fromisoformat("2026-10-08T12:00:00+00:00"),
            )

            observations = store.learning_observations_by_ticker()["AAA"]
            self.assertEqual(len(observations), 1)
            self.assertAlmostEqual(observations[0].outcome_return, (103 / 200 - 1) - .002)

            quality = store.summary()["learning_data_quality"]
            self.assertEqual(quality["anchored_decisions"], 2)
            self.assertEqual(quality["unique_ticker_sessions"], 1)
            self.assertEqual(quality["unique_session_dates"], 1)
            self.assertEqual(quality["duplicate_decisions_excluded"], 1)
            self.assertEqual(quality["duplicate_scored_observations_excluded"], 1)
            self.assertEqual(quality["learning_observations_after_deduplication"], 1)



    def test_later_wait_does_not_discard_matured_buy_learning_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            as_of = datetime.fromisoformat("2026-10-02T12:00:00+00:00")
            history = [candle("2026-10-01", 100)]

            store.record_cycle(
                "early-buy",
                {"AAA": SimpleNamespace(action="BUY", reason="valid signal")},
                [],
                equity=1000, cash=1000, total_commissions=0,
                current_prices={"AAA": 100},
                candle_history={"AAA": history},
                intelligence_results={"AAA": intelligence_snapshot()},
                commission_rate=.001,
                as_of=as_of,
            )
            # A later WAIT on the same ticker/session must not overwrite the
            # only trainable directional prediction for that session.
            store.record_cycle(
                "late-wait",
                {"AAA": SimpleNamespace(action="WAIT", reason="no signal")},
                [],
                equity=1000, cash=1000, total_commissions=0,
                current_prices={"AAA": 100},
                candle_history={"AAA": history},
                intelligence_results={"AAA": intelligence_snapshot()},
                commission_rate=.001,
                as_of=as_of + timedelta(minutes=5),
            )
            future = [
                candle("2026-10-05", 101),
                candle("2026-10-06", 102),
                candle("2026-10-07", 103),
            ]
            store.record_cycle(
                "maturity-cycle", {}, [], equity=1000, cash=1000, total_commissions=0,
                candle_history={"AAA": history + future},
                commission_rate=.001,
                as_of=datetime.fromisoformat("2026-10-08T12:00:00+00:00"),
            )

            observations = store.learning_observations_by_ticker()["AAA"]
            self.assertEqual(len(observations), 1)
            self.assertTrue(observations[0].correct)
            self.assertEqual(observations[0].decision_time, as_of.isoformat())
            quality = store.summary()["learning_data_quality"]
            self.assertEqual(quality["unique_ticker_sessions"], 1)
            self.assertEqual(quality["duplicate_scored_observations_excluded"], 0)
            self.assertEqual(quality["learning_observations_after_deduplication"], 1)

    def test_daily_candle_completion_excludes_same_day_close_to_prevent_leakage(self):
        before_close_buffer = datetime.fromisoformat("2026-10-14T15:59:00+00:00")
        after_close_buffer = datetime.fromisoformat("2026-10-14T16:00:00+00:00")
        previous_day = candle("2026-10-13", 100)
        current_day_candle = candle("2026-10-14", 101)

        self.assertTrue(DecisionAuditStore._is_completed_daily_candle(previous_day, now=before_close_buffer))
        self.assertFalse(DecisionAuditStore._is_completed_daily_candle(current_day_candle, now=before_close_buffer))
        self.assertFalse(DecisionAuditStore._is_completed_daily_candle(current_day_candle, now=after_close_buffer))

    def test_daily_candle_completion_handles_weekends_and_date_only_values(self):
        saturday_morning = datetime.fromisoformat("2026-10-17T08:00:00+00:00")
        friday = candle("2026-10-16", 100)
        saturday = candle("2026-10-17", 101)
        date_only_today = SimpleNamespace(time=__import__("datetime").date(2026, 10, 17))

        self.assertTrue(DecisionAuditStore._is_completed_daily_candle(friday, now=saturday_morning))
        self.assertFalse(DecisionAuditStore._is_completed_daily_candle(saturday, now=saturday_morning))
        self.assertFalse(DecisionAuditStore._is_completed_daily_candle(date_only_today, now=saturday_morning))


    def test_price_rejects_non_finite_and_non_positive_values(self):
        for value in (float("nan"), float("inf"), float("-inf"), 0, -1):
            with self.subTest(value=value):
                self.assertIsNone(DecisionAuditStore._price(value))

        self.assertEqual(DecisionAuditStore._price(100), 100.0)
        self.assertEqual(
            DecisionAuditStore._price(SimpleNamespace(units=100, nano=500_000_000)),
            100.5,
        )


if __name__ == "__main__":
    unittest.main()
