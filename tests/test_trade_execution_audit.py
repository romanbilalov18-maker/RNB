from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sqlite3
import unittest

from bot.decision_audit import DecisionAuditStore
from bot.portfolio_store import SQLitePortfolioStore
from bot.virtual_portfolio import VirtualPortfolio


class TradeExecutionAuditTests(unittest.TestCase):
    def test_trade_reason_and_entry_price_survive_portfolio_round_trip(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            store = SQLitePortfolioStore(path)
            portfolio = VirtualPortfolio(initial_balance=10000, commission_rate=0.0005)
            timestamp = datetime(2026, 10, 14, tzinfo=timezone.utc)

            portfolio.buy(
                "TEST", 10, 100.0, timestamp,
                reason="DecisionEngine BUY: score passed",
            )
            sell = portfolio.sell(
                "TEST", 10, 101.0, timestamp,
                reason="достигнут Take Profit +0.15%",
            )
            store.save(portfolio)
            restored = store.load_or_create(10000, 0.0005)

            self.assertEqual(len(restored.trades), 2)
            self.assertEqual(restored.trades[0].reason, "DecisionEngine BUY: score passed")
            self.assertEqual(restored.trades[0].entry_price, 100.0)
            self.assertEqual(restored.trades[1].reason, "достигнут Take Profit +0.15%")
            self.assertEqual(restored.trades[1].entry_price, 100.0)
            self.assertAlmostEqual(restored.trades[1].realized_pnl, sell.realized_pnl)

    def test_execution_reason_and_prices_are_written_to_decision_audit(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "decision_audit.sqlite3"
            audit = DecisionAuditStore(path)
            timestamp = datetime(2026, 10, 14, tzinfo=timezone.utc)
            portfolio = VirtualPortfolio(initial_balance=10000, commission_rate=0.0005)
            portfolio.buy("TEST", 10, 100.0, timestamp, reason="BUY signal accepted")
            sell = portfolio.sell("TEST", 10, 99.0, timestamp, reason="negative momentum and trend")

            audit.record_cycle(
                cycle_id="cycle-1",
                decisions={"TEST": SimpleNamespace(
                    action="SELL", reason="recommendation reason",
                    score=0.2, confidence=0.4, consistency=0.5,
                )},
                virtual_trades=[sell],
                equity=9990.0,
                cash=9990.0,
                total_commissions=0.995,
            )

            with sqlite3.connect(path) as db:
                row = db.execute(
                    "SELECT execution_reason, entry_price, execution_price, realized_pnl "
                    "FROM decision_audit WHERE cycle_id='cycle-1' AND ticker='TEST'"
                ).fetchone()

            self.assertEqual(row[0], "negative momentum and trend")
            self.assertEqual(row[1], 100.0)
            self.assertEqual(row[2], 99.0)
            self.assertAlmostEqual(row[3], sell.realized_pnl)


if __name__ == "__main__":
    unittest.main()
