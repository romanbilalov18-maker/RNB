import tempfile
import sqlite3
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bot.models import VirtualPosition
from bot.portfolio_store import SQLitePortfolioStore
from bot.virtual_portfolio import VirtualPortfolio


class TestSQLitePortfolioStore(unittest.TestCase):
    def test_round_trip_preserves_portfolio_and_trades(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            store = SQLitePortfolioStore(path)

            portfolio = VirtualPortfolio(10_000, commission_rate=0.001)
            timestamp = datetime.now(timezone.utc)
            portfolio.buy("TEST", 10, 100, timestamp)
            store.save(portfolio)

            restored = store.load_or_create(20_000, 0.002)

            self.assertEqual(restored.initial_balance, 10_000)
            self.assertEqual(restored.commission_rate, 0.001)
            self.assertAlmostEqual(restored.cash, 8_999)
            self.assertEqual(restored.positions["TEST"].quantity, 10)
            self.assertEqual(restored.positions["TEST"].average_price, 100)
            self.assertEqual(len(restored.trades), 1)
            self.assertEqual(restored.trades[0].ticker, "TEST")

    def test_rejects_corrupt_persisted_position_quantity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            store = SQLitePortfolioStore(path)
            portfolio = VirtualPortfolio(10_000)
            portfolio.buy("TEST", 2, 100.0, datetime.now(timezone.utc))
            store.save(portfolio)
            with sqlite3.connect(path) as db:
                db.execute("UPDATE positions SET quantity=0 WHERE ticker='TEST'")

            with self.assertRaisesRegex(ValueError, "position TEST quantity"):
                SQLitePortfolioStore(path).load_or_create(1.0, 0.0)

    def test_rejects_corrupt_persisted_position_price(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            store = SQLitePortfolioStore(path)
            portfolio = VirtualPortfolio(10_000)
            portfolio.buy("TEST", 2, 100.0, datetime.now(timezone.utc))
            store.save(portfolio)
            with sqlite3.connect(path) as db:
                db.execute("UPDATE positions SET average_price=-1 WHERE ticker='TEST'")

            with self.assertRaisesRegex(ValueError, "average_price"):
                SQLitePortfolioStore(path).load_or_create(1.0, 0.0)

    def test_rejects_naive_persisted_trade_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            store = SQLitePortfolioStore(path)
            portfolio = VirtualPortfolio(10_000)
            portfolio.buy("TEST", 2, 100.0, datetime.now(timezone.utc))
            store.save(portfolio)
            with sqlite3.connect(path) as db:
                db.execute("UPDATE trades SET timestamp='2026-10-31T12:00:00'")

            with self.assertRaisesRegex(ValueError, "must include a timezone"):
                SQLitePortfolioStore(path).load_or_create(1.0, 0.0)

    def test_restores_valid_negative_realized_pnl_from_sell_trade(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            store = SQLitePortfolioStore(path)
            timestamp = datetime.now(timezone.utc)
            portfolio = VirtualPortfolio(10_000)
            portfolio.buy("TEST", 2, 100.0, timestamp)
            portfolio.sell("TEST", 2, 90.0, timestamp)
            store.save(portfolio)

            restored = SQLitePortfolioStore(path).load_or_create(1.0, 0.0)
            self.assertLess(restored.trades[-1].realized_pnl, 0)
            self.assertLess(restored.realized_pnl, 0)

    def test_position_health_counters_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            store = SQLitePortfolioStore(path)
            portfolio = VirtualPortfolio(10_000)
            portfolio.buy("HEALTH", 2, 100, datetime.now(timezone.utc))
            position = portfolio.positions["HEALTH"]
            position.quote_unavailable_cycles = 7
            position.stagnant_sessions = 5
            position.last_health_status = "QUOTE_UNAVAILABLE"
            position.last_health_candle_timestamp = "2026-10-30T20:00:00+00:00"

            store.save(portfolio)
            restored = SQLitePortfolioStore(path).load_or_create(1.0, 0.0)
            restored_position = restored.positions["HEALTH"]

            self.assertEqual(restored_position.quote_unavailable_cycles, 7)
            self.assertEqual(restored_position.stagnant_sessions, 5)
            self.assertEqual(restored_position.last_health_status, "QUOTE_UNAVAILABLE")
            self.assertEqual(
                restored_position.last_health_candle_timestamp,
                "2026-10-30T20:00:00+00:00",
            )

    def test_partial_sale_commissions_and_reserve_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            store = SQLitePortfolioStore(path)
            timestamp = datetime(2026, 10, 20, tzinfo=timezone.utc)
            portfolio = VirtualPortfolio(10_000, commission_rate=0.001)
            portfolio.buy("TEST", 10, 100.0, timestamp)
            portfolio.sell("TEST", 4, 110.0, timestamp)
            store.save(portfolio, {"TEST": 110.0})

            restored = SQLitePortfolioStore(path).load_or_create(1.0, 0.0)

            self.assertEqual(restored.positions["TEST"].quantity, 6)
            self.assertAlmostEqual(restored.cash, 9411.148)
            self.assertAlmostEqual(restored.protected_cash, 27.412)
            self.assertAlmostEqual(restored.commissions, 1.44)
            self.assertAlmostEqual(restored.realized_pnl, 39.16)
            self.assertEqual([trade.side for trade in restored.trades], ["BUY", "SELL"])
            self.assertAlmostEqual(restored.trades[1].commission, 0.44)
            self.assertAlmostEqual(restored.trades[1].realized_pnl, 39.16)
            self.assertAlmostEqual(restored.trades[1].reserve_transfer, 27.412)
            self.assertAlmostEqual(restored.equity({"TEST": 110.0}), 10098.56)
    def test_profit_reserve_rate_survives_restart_and_controls_next_sale(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            store = SQLitePortfolioStore(path)
            timestamp = datetime(2026, 10, 20, tzinfo=timezone.utc)
            portfolio = VirtualPortfolio(
                10_000,
                commission_rate=0.001,
                profit_reserve_rate=0.35,
            )
            portfolio.buy("TEST", 10, 100.0, timestamp)
            store.save(portfolio)

            restored = SQLitePortfolioStore(path).load_or_create(1.0, 0.0)
            self.assertAlmostEqual(restored.profit_reserve_rate, 0.35)
            restored.sell("TEST", 10, 110.0, timestamp)

            self.assertAlmostEqual(restored.protected_cash, 34.265)
            self.assertAlmostEqual(restored.cash, 10063.635)

    def test_equity_history_tracks_market_revaluation_across_saves(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePortfolioStore(Path(directory) / "portfolio.sqlite3")
            portfolio = VirtualPortfolio(10_000, commission_rate=0.001)
            portfolio.buy("TEST", 10, 100, datetime.now(timezone.utc))

            store.save(portfolio, {"TEST": 100})
            store.save(portfolio, {"TEST": 120})

            history = store.equity_history()
            self.assertEqual(len(history), 3)
            self.assertAlmostEqual(history[0], 10_000.0)
            self.assertAlmostEqual(history[1], 9_999.0)
            self.assertAlmostEqual(history[2], 10_199.0)

            restored = store.load_or_create(20_000, 0.002)
            self.assertAlmostEqual(restored.equity({"TEST": 120}), 10_199.0)
            self.assertEqual(len(restored.trades), 1)
            self.assertEqual(restored.positions["TEST"].quantity, 10)

    def test_drawdown_uses_equity_history_across_store_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            store = SQLitePortfolioStore(path)
            portfolio = VirtualPortfolio(10_000, commission_rate=0.001)
            portfolio.buy("TEST", 10, 100, datetime.now(timezone.utc))

            store.save(portfolio, {"TEST": 100})
            store.save(portfolio, {"TEST": 80})

            # Simulate a process restart by constructing a new store instance.
            restarted_store = SQLitePortfolioStore(path)
            restored = restarted_store.load_or_create(10_000, 0.001)
            restarted_store.save(restored, {"TEST": 90})

            history = restarted_store.equity_history()
            current_equity = restored.equity({"TEST": 90})
            stats = restored.statistics(current_equity, history)

            self.assertEqual(len(history), 4)
            self.assertAlmostEqual(history[0], 10_000.0)
            self.assertAlmostEqual(history[1], 9_999.0)
            self.assertAlmostEqual(history[2], 9_799.0)
            self.assertAlmostEqual(history[3], 9_899.0)
            self.assertAlmostEqual(stats.peak_equity, 10_000.0)
            self.assertAlmostEqual(stats.max_drawdown, 201.0)
            self.assertAlmostEqual(stats.max_drawdown_pct, 201.0 / 10_000.0 * 100.0)

    def test_first_equity_snapshot_keeps_initial_capital_as_drawdown_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePortfolioStore(Path(directory) / "portfolio.sqlite3")
            portfolio = VirtualPortfolio(10_000, commission_rate=0.001)
            portfolio.buy("TEST", 10, 100, datetime.now(timezone.utc))

            store.save(portfolio, {"TEST": 80})

            history = store.equity_history()
            self.assertEqual(history, [10_000.0, 9_799.0])
            stats = portfolio.statistics(history[-1], history)
            self.assertEqual(stats.peak_equity, 10_000.0)
            self.assertAlmostEqual(stats.max_drawdown, 201.0)
            self.assertAlmostEqual(stats.max_drawdown_pct, 2.01)

    def test_missing_market_price_saves_portfolio_without_partial_equity_history(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePortfolioStore(Path(directory) / "portfolio.sqlite3")
            portfolio = VirtualPortfolio(10_000)
            portfolio.buy("TEST", 1, 100, datetime.now(timezone.utc))
            store.save(portfolio, {"TEST": 100})
            history_before = store.equity_history()

            portfolio.buy("OTHER", 1, 50, datetime.now(timezone.utc))
            store.save(portfolio, {})

            self.assertEqual(store.equity_history(), history_before)
            restored = store.load_or_create(10_000, 0.0005)
            self.assertEqual(restored.positions["TEST"].quantity, 1)
            self.assertEqual(restored.positions["OTHER"].quantity, 1)
            self.assertEqual(len(restored.trades), 2)

    def test_round_trip_preserves_protected_profit_reserve(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            store = SQLitePortfolioStore(path)
            portfolio = VirtualPortfolio(10_000, commission_rate=0.001)
            portfolio.protected_cash = 350.75
            portfolio.cash = 8_500.25
            portfolio.realized_pnl = 1_000.0
            store.save(portfolio)

            restored = SQLitePortfolioStore(path).load_or_create(
                initial_balance=20_000,
                commission_rate=0.002,
            )

            self.assertEqual(restored.initial_balance, 10_000)
            self.assertAlmostEqual(restored.protected_cash, 350.75)
            self.assertAlmostEqual(restored.cash, 8_500.25)
            self.assertAlmostEqual(restored.realized_pnl, 1_000.0)

    def test_failed_trade_batch_rolls_back_every_portfolio_table(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            store = SQLitePortfolioStore(path)
            timestamp = datetime.now(timezone.utc)
            portfolio = VirtualPortfolio(10_000, commission_rate=0.001)
            portfolio.buy("KEEP", 1, 100, timestamp)
            store.save(portfolio, {"KEEP": 100})

            with store._connect() as db:
                before_portfolio = tuple(db.execute(
                    "SELECT initial_balance, commission_rate, cash, realized_pnl, commissions, "
                    "protected_cash, profit_reserve_rate FROM portfolio WHERE id=1"
                ).fetchone())
                before_positions = [tuple(row) for row in db.execute(
                    "SELECT ticker, quantity, average_price FROM positions ORDER BY ticker"
                )]
                before_trades = [tuple(row) for row in db.execute(
                    "SELECT timestamp, ticker, side, quantity, price, commission, realized_pnl, reason, entry_price "
                    "FROM trades ORDER BY id"
                )]
                before_equity = [tuple(row) for row in db.execute(
                    "SELECT timestamp, equity FROM equity_history ORDER BY id"
                )]

            portfolio.buy("NEW", 1, 50, timestamp)
            # The reserve setting is part of the same atomic account snapshot.
            # A later write failure must roll it back along with balances/trades.
            portfolio.profit_reserve_rate = 0.35
            # Two mapping entries claim the same persisted ticker. SQLite's
            # positions primary key must reject the second insert after the
            # portfolio upsert and position delete have already run.
            portfolio.positions["ALIAS"] = VirtualPosition("KEEP", 1, 75.0)
            with self.assertRaisesRegex(Exception, "UNIQUE constraint failed"):
                store.save(portfolio, {"KEEP": 100, "NEW": 50})

            with store._connect() as db:
                after_portfolio = tuple(db.execute(
                    "SELECT initial_balance, commission_rate, cash, realized_pnl, commissions, "
                    "protected_cash, profit_reserve_rate FROM portfolio WHERE id=1"
                ).fetchone())
                after_positions = [tuple(row) for row in db.execute(
                    "SELECT ticker, quantity, average_price FROM positions ORDER BY ticker"
                )]
                after_trades = [tuple(row) for row in db.execute(
                    "SELECT timestamp, ticker, side, quantity, price, commission, realized_pnl, reason, entry_price "
                    "FROM trades ORDER BY id"
                )]
                after_equity = [tuple(row) for row in db.execute(
                    "SELECT timestamp, equity FROM equity_history ORDER BY id"
                )]

            self.assertEqual(after_portfolio, before_portfolio)
            self.assertEqual(after_positions, before_positions)
            self.assertEqual(after_trades, before_trades)
            self.assertEqual(after_equity, before_equity)

            # The failed transaction must leave a database that can be reopened
            # and used, not merely rows that look unchanged on this connection.
            with store._connect() as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

            restored = SQLitePortfolioStore(path).load_or_create(1.0, 0.0)
            self.assertEqual(
                [(p.ticker, p.quantity, p.average_price) for p in restored.positions.values()],
                [(row[0], row[1], row[2]) for row in before_positions],
            )
            self.assertEqual(len(restored.trades), len(before_trades))
            self.assertAlmostEqual(restored.cash, before_portfolio[2])
            self.assertAlmostEqual(restored.profit_reserve_rate, before_portfolio[6])
            self.assertAlmostEqual(restored.profit_reserve_rate, 0.7)

    def test_missing_portfolio_row_with_residual_state_fails_closed_without_deleting_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            store = SQLitePortfolioStore(path)
            portfolio = store.load_or_create(10_000, 0.001)
            timestamp = datetime(2026, 10, 20, tzinfo=timezone.utc)
            portfolio.buy("KEEP", 2, 100.0, timestamp)
            store.save(portfolio, {"KEEP": 100.0})

            # Simulate a damaged/incompletely restored database: the account
            # singleton is missing, while positions and trade history survive.
            with store._connect() as db:
                db.execute("DELETE FROM portfolio WHERE id=1")
                db.commit()

            with self.assertRaisesRegex(RuntimeError, "refusing to create a new portfolio"):
                SQLitePortfolioStore(path).load_or_create(50_000, 0.005)

            # A failed recovery attempt must not erase the remaining durable data.
            with store._connect() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM portfolio").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM positions").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM trades").fetchone()[0], 1)
                self.assertEqual(tuple(db.execute("SELECT ticker, quantity FROM positions").fetchone()), ("KEEP", 2))
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_missing_portfolio_row_with_only_cycle_history_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            store = SQLitePortfolioStore(path)
            store.load_or_create(10_000, 0.001)
            with store._connect() as db:
                db.execute(
                    "INSERT INTO committed_cycles (cycle_id, committed_at) VALUES (?, ?)",
                    ("previously-committed", "test"),
                )
                db.execute("DELETE FROM portfolio WHERE id=1")
                db.commit()

            with self.assertRaisesRegex(RuntimeError, "committed_cycles"):
                SQLitePortfolioStore(path).load_or_create(10_000, 0.001)

            with store._connect() as db:
                self.assertEqual(
                    db.execute("SELECT cycle_id FROM committed_cycles").fetchone()[0],
                    "previously-committed",
                )

    def test_new_store_creates_initial_portfolio(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePortfolioStore(Path(directory) / "portfolio.sqlite3")

            portfolio = store.load_or_create(10_000, 0.001)

            self.assertEqual(portfolio.cash, 10_000)
            self.assertEqual(portfolio.positions, {})
            self.assertEqual(portfolio.trades, [])

    def test_migrates_legacy_portfolio_schema_without_losing_financial_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            timestamp = datetime(2025, 1, 2, tzinfo=timezone.utc).isoformat()
            with sqlite3.connect(path) as db:
                db.executescript(
                    """
                    CREATE TABLE portfolio (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        initial_balance REAL NOT NULL,
                        commission_rate REAL NOT NULL,
                        cash REAL NOT NULL,
                        realized_pnl REAL NOT NULL,
                        commissions REAL NOT NULL
                    );
                    INSERT INTO portfolio VALUES (1, 10000, 0.001, 8999, 0, 1);
                    CREATE TABLE positions (
                        ticker TEXT PRIMARY KEY,
                        quantity INTEGER NOT NULL,
                        average_price REAL NOT NULL
                    );
                    INSERT INTO positions VALUES ('TEST', 10, 100);
                    CREATE TABLE trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        ticker TEXT NOT NULL,
                        side TEXT NOT NULL,
                        quantity INTEGER NOT NULL,
                        price REAL NOT NULL,
                        commission REAL NOT NULL,
                        realized_pnl REAL NOT NULL
                    );
                    """
                )
                db.execute(
                    "INSERT INTO trades (timestamp, ticker, side, quantity, price, commission, realized_pnl) "
                    "VALUES (?, 'TEST', 'BUY', 10, 100, 1, 0)",
                    (timestamp,),
                )
                db.commit()

            store = SQLitePortfolioStore(path)
            restored = store.load_or_create(50_000, 0.005)

            self.assertEqual(restored.initial_balance, 10_000)
            self.assertAlmostEqual(restored.cash, 8_999)
            self.assertAlmostEqual(restored.commissions, 1)
            self.assertAlmostEqual(restored.protected_cash, 0)
            self.assertAlmostEqual(restored.profit_reserve_rate, 0.7)
            self.assertEqual(restored.positions["TEST"].quantity, 10)
            self.assertEqual(len(restored.trades), 1)
            self.assertEqual(restored.trades[0].reason, "not recorded")
            self.assertIsNone(restored.trades[0].entry_price)

    def test_reconciles_repeated_buys_partial_sales_and_full_close_after_restarts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            timestamp = datetime(2026, 10, 20, tzinfo=timezone.utc)
            store = SQLitePortfolioStore(path)
            portfolio = VirtualPortfolio(10_000, commission_rate=0.001, profit_reserve_rate=0.4)

            portfolio.buy("TEST", 4, 100.0, timestamp)
            store.save(portfolio)
            portfolio = SQLitePortfolioStore(path).load_or_create(1, 0)
            portfolio.buy("TEST", 6, 120.0, timestamp)
            store.save(portfolio)
            portfolio = SQLitePortfolioStore(path).load_or_create(1, 0)
            self.assertAlmostEqual(portfolio.positions["TEST"].average_price, 112.0)

            portfolio.sell("TEST", 3, 130.0, timestamp)
            store.save(portfolio)
            portfolio = SQLitePortfolioStore(path).load_or_create(1, 0)
            portfolio.buy("TEST", 2, 90.0, timestamp)
            store.save(portfolio)
            portfolio = SQLitePortfolioStore(path).load_or_create(1, 0)
            portfolio.sell("TEST", 4, 115.0, timestamp)
            store.save(portfolio)
            portfolio = SQLitePortfolioStore(path).load_or_create(1, 0)
            portfolio.sell("TEST", 5, 110.0, timestamp)

            self.assertEqual(portfolio.positions, {})
            self.assertAlmostEqual(portfolio.realized_pnl, sum(
                trade.realized_pnl for trade in portfolio.trades if trade.side == "SELL"
            ))
            self.assertAlmostEqual(portfolio.commissions, sum(
                trade.commission for trade in portfolio.trades
            ))
            self.assertAlmostEqual(
                portfolio.cash + portfolio.protected_cash,
                portfolio.initial_balance + portfolio.realized_pnl,
            )


if __name__ == "__main__":
    unittest.main()
