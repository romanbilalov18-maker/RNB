import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bot.decision_audit import DecisionAuditStore
from bot.main import CycleConsistencyError, _persist_cycle_safely
from bot.portfolio_store import SQLitePortfolioStore


class PersistenceSafetyTests(unittest.TestCase):
    def test_portfolio_save_failure_rolls_back_audit_cycle(self):
        audit = Mock()
        audit.record_cycle.return_value = 3
        portfolio_store = Mock()
        save_error = OSError("disk full")
        portfolio_store.save.side_effect = save_error

        with patch("bot.main.time.sleep"):
            with self.assertRaisesRegex(OSError, "disk full"):
                _persist_cycle_safely(
                    portfolio_store,
                    audit,
                    object(),
                    {},
                    cycle_id="cycle-test",
                )

        audit.record_cycle.assert_called_once_with(cycle_id="cycle-test")
        audit.delete_cycle.assert_called_once_with("cycle-test")

    def test_failed_audit_rollback_raises_fatal_consistency_error(self):
        audit = Mock()
        audit.record_cycle.return_value = 1
        audit.delete_cycle.side_effect = OSError("audit database unavailable")
        portfolio_store = Mock()
        portfolio_store.save.side_effect = OSError("portfolio database full")

        with self.assertRaisesRegex(CycleConsistencyError, "manual reconciliation"):
            _persist_cycle_safely(
                portfolio_store,
                audit,
                object(),
                {},
                cycle_id="cycle-test",
            )

        audit.delete_cycle.assert_called_once_with("cycle-test")

    def test_failed_save_retry_keeps_exactly_one_durable_trade(self):
        with tempfile.TemporaryDirectory() as directory:
            portfolio_path = Path(directory) / "portfolio.sqlite3"
            audit_path = Path(directory) / "audit.sqlite"
            portfolio_store = SQLitePortfolioStore(portfolio_path)
            audit_store = DecisionAuditStore(audit_path)
            portfolio = portfolio_store.load_or_create(10_000, 0.001)
            timestamp = datetime(2026, 10, 20, tzinfo=timezone.utc)
            trade = portfolio.buy("AAA", 1, 100.0, timestamp)
            decision = SimpleNamespace(
                action="BUY", reason="isolated regression fixture",
                score=0.8, confidence=0.8, consistency=0.8,
            )

            with patch.object(portfolio_store, "save", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    _persist_cycle_safely(
                        portfolio_store, audit_store, portfolio, {"AAA": 100.0},
                        cycle_id="failed-cycle",
                        decisions={"AAA": decision},
                        virtual_trades=[trade],
                        equity=portfolio.equity({"AAA": 100.0}),
                        cash=portfolio.cash,
                        total_commissions=portfolio.commissions,
                        current_prices={"AAA": 100.0},
                        commission_rate=portfolio.commission_rate,
                    )

            # The failed write must not leave an orphaned audit trade or durable
            # portfolio mutation. Restart from disk, not the mutated local object.
            self.assertEqual(audit_store.summary()["observations"], 0)
            restarted = SQLitePortfolioStore(portfolio_path).load_or_create(10_000, 0.001)
            self.assertEqual(restarted.trades, [])
            self.assertEqual(restarted.positions, {})
            self.assertAlmostEqual(restarted.cash, 10_000.0)

            retry_trade = restarted.buy("AAA", 1, 100.0, timestamp)
            _persist_cycle_safely(
                portfolio_store, audit_store, restarted, {"AAA": 100.0},
                cycle_id="retry-cycle",
                decisions={"AAA": decision},
                virtual_trades=[retry_trade],
                equity=restarted.equity({"AAA": 100.0}),
                cash=restarted.cash,
                total_commissions=restarted.commissions,
                current_prices={"AAA": 100.0},
                commission_rate=restarted.commission_rate,
            )

            restored_again = SQLitePortfolioStore(portfolio_path).load_or_create(1.0, 0.0)
            self.assertEqual(len(restored_again.trades), 1)
            self.assertEqual(restored_again.positions["AAA"].quantity, 1)
            self.assertAlmostEqual(restored_again.commissions, 0.1)
            self.assertAlmostEqual(restored_again.cash, 9_899.9)
            summary = DecisionAuditStore(audit_path).summary()
            self.assertEqual(summary["observations"], 1)
            self.assertAlmostEqual(summary["recorded_trade_commissions"], 0.1)

    def test_audit_write_failure_does_not_save_portfolio(self):
        audit = Mock()
        audit.record_cycle.side_effect = OSError("audit unavailable")
        portfolio_store = Mock()

        with patch("bot.main.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "after 3 attempts"):
                _persist_cycle_safely(
                    portfolio_store,
                    audit,
                    object(),
                    {},
                    cycle_id="cycle-test",
                )

        self.assertEqual(audit.record_cycle.call_count, 3)
        portfolio_store.save.assert_not_called()
        audit.delete_cycle.assert_not_called()


if __name__ == "__main__":
    unittest.main()
