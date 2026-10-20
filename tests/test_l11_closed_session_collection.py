import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from bot.decision_audit import DecisionAuditStore
from bot.main import _persist_cycle_safely


def candle(day, close):
    return SimpleNamespace(
        time=datetime.fromisoformat(day).replace(tzinfo=timezone.utc),
        close=close,
    )


class ClosedSessionOutcomeCollectionTests(unittest.TestCase):
    def test_collects_completed_prices_and_matures_outcomes_without_new_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            as_of = datetime.fromisoformat("2026-10-02T12:00:00+00:00")
            store.record_cycle(
                "anchor",
                {"AAA": SimpleNamespace(action="BUY", reason="test")},
                [],
                equity=1000,
                cash=1000,
                total_commissions=0,
                current_prices={"AAA": 100},
                intelligence_results={"AAA": SimpleNamespace(
                    **{
                        f"level_{number:02d}": SimpleNamespace(
                            score=0.7, analyzer_results=(), metadata={}
                        )
                        for number in range(1, 16)
                    }
                )},
                as_of=as_of,
            )
            prices = {
                "AAA": [
                    candle("2026-10-05", 101),
                    candle("2026-10-06", 102),
                    candle("2026-10-07", 103),
                    candle("2026-10-10", 999),  # Saturday must be ignored.
                    candle("2026-10-08", -1),   # Invalid price must be ignored.
                ]
            }
            result = store.record_market_session_prices(
                prices, as_of=datetime.fromisoformat("2026-10-12T12:00:00+00:00")
            )
            self.assertEqual(result, {
                "prices_added": 3, "prices_updated": 0, "outcomes_added": 2
            })
            summary = store.summary()
            self.assertEqual(summary["observations"], 1)
            self.assertEqual(summary["learning_observations"], 1)
            with store._connect() as db:
                saved = db.execute(
                    "SELECT session_date, close_price FROM market_session_prices "
                    "WHERE ticker='AAA' ORDER BY session_date"
                ).fetchall()
                horizons = db.execute(
                    "SELECT horizon_sessions FROM decision_outcomes ORDER BY horizon_sessions"
                ).fetchall()
            self.assertEqual(
                [(row["session_date"], row["close_price"]) for row in saved],
                [("2026-10-05", 101), ("2026-10-06", 102), ("2026-10-07", 103)],
            )
            self.assertEqual([row["horizon_sessions"] for row in horizons], [1, 3])

            repeated = store.record_market_session_prices(
                prices, as_of=datetime.fromisoformat("2026-10-12T12:00:00+00:00")
            )
            self.assertEqual(repeated, {
                "prices_added": 0, "prices_updated": 0, "outcomes_added": 0
            })
            self.assertEqual(store.summary()["observations"], 1)

    def test_delete_cycle_removes_audit_and_derived_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            store.record_cycle(
                "failed-save",
                {"AAA": SimpleNamespace(action="WAIT", reason="test")},
                [],
                equity=1000, cash=1000, total_commissions=0,
            )
            self.assertEqual(store.delete_cycle("failed-save"), 1)
            self.assertEqual(store.delete_cycle("failed-save"), 0)
            self.assertEqual(store.summary()["observations"], 0)

    def test_portfolio_save_failure_rolls_back_audit_cycle(self):
        portfolio_store = Mock()
        portfolio_store.save.side_effect = OSError("disk full")
        audit_store = Mock()
        audit_store.record_cycle.return_value = 1
        with self.assertRaisesRegex(OSError, "disk full"):
            _persist_cycle_safely(
                portfolio_store, audit_store, object(), {},
                cycle_id="cycle-1", decisions={}, virtual_trades=[],
                equity=1000, cash=1000, total_commissions=0,
            )
        audit_store.delete_cycle.assert_called_once_with("cycle-1")

    def test_audit_failure_prevents_portfolio_save(self):
        portfolio_store = Mock()
        audit_store = Mock()
        audit_store.record_cycle.side_effect = OSError("audit unavailable")
        with self.assertRaisesRegex(RuntimeError, "failed after 3 attempts"):
            _persist_cycle_safely(
                portfolio_store, audit_store, object(), {},
                cycle_id="cycle-1", decisions={}, virtual_trades=[],
                equity=1000, cash=1000, total_commissions=0,
            )
        portfolio_store.save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
