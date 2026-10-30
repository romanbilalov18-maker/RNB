import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from bot.models import VirtualPosition
from bot.paper_executor import PaperExecutor
from bot.portfolio_store import SQLitePortfolioStore
from bot.virtual_portfolio import VirtualPortfolio


class PositionSessionGuardTests(unittest.TestCase):
    def _scan(self, session, exchange):
        return SimpleNamespace(
            analyses={},
            buy_candidates=[],
            current_prices={"TEST": 110.0},
            previous_closes={},
            lot_sizes={},
            active_trading_tickers={"TEST"},
            fresh_quote_tickers={"TEST"},
            sellable_quote_tickers=set(),
            session_by_ticker={
                "TEST": {
                    "session": session,
                    "instrument_exchange": exchange,
                }
            },
        )

    def test_position_is_not_managed_in_different_exchange_session(self):
        portfolio = VirtualPortfolio(initial_balance=10_000, commission_rate=0.0)
        portfolio.positions["TEST"] = VirtualPosition(
            "TEST", 10, 100.0,
            purchase_timestamp=datetime(2026, 10, 20, 10, tzinfo=timezone.utc),
            purchase_session="MORNING",
            purchase_exchange="MOEX",
        )

        sells, buys = PaperExecutor().execute(
            portfolio,
            self._scan("EVENING", "MOEX"),
            eligible_buy_tickers=set(),
        )

        self.assertEqual(sells, [])
        self.assertEqual(buys, [])
        self.assertEqual(portfolio.positions["TEST"].quantity, 10)

    def test_position_is_not_managed_when_exchange_differs(self):
        portfolio = VirtualPortfolio(initial_balance=10_000, commission_rate=0.0)
        portfolio.positions["TEST"] = VirtualPosition(
            "TEST", 10, 100.0,
            purchase_timestamp=datetime(2026, 10, 20, 10, tzinfo=timezone.utc),
            purchase_session="MORNING",
            purchase_exchange="MOEX",
        )

        sells, _ = PaperExecutor().execute(
            portfolio,
            self._scan("MORNING", "OTHER_EXCHANGE"),
            eligible_buy_tickers=set(),
        )

        self.assertEqual(sells, [])
        self.assertEqual(portfolio.positions["TEST"].quantity, 10)

    def test_position_metadata_survives_store_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.sqlite3"
            store = SQLitePortfolioStore(path)
            portfolio = VirtualPortfolio(initial_balance=10_000, commission_rate=0.001)
            purchased_at = datetime(2026, 10, 20, 10, 30, tzinfo=timezone.utc)
            portfolio.positions["TEST"] = VirtualPosition(
                "TEST", 10, 100.25,
                purchase_timestamp=purchased_at,
                purchase_session="MORNING",
                purchase_exchange="MOEX",
            )
            store.save(portfolio)

            # A new store instance models a separate process after restart.
            restored = SQLitePortfolioStore(path).load_or_create(1.0, 0.0)
            position = restored.positions["TEST"]

            self.assertEqual(position.quantity, 10)
            self.assertEqual(position.average_price, 100.25)
            self.assertEqual(position.purchase_timestamp, purchased_at)
            self.assertEqual(position.purchase_session, "MORNING")
            self.assertEqual(position.purchase_exchange, "MOEX")

    def test_legacy_position_without_entry_metadata_ignores_strategy_sell_signal(self):
        portfolio = VirtualPortfolio(initial_balance=10_000, commission_rate=0.0)
        portfolio.positions["TEST"] = VirtualPosition("TEST", 10, 100.0)
        bearish = SimpleNamespace(momentum=-0.10, trend_strength=-0.10)
        scan = self._scan("MORNING", "MOEX")
        scan.current_prices["TEST"] = 100.0
        scan.analyses = {"TEST": bearish}

        sells, buys = PaperExecutor().execute(
            portfolio, scan, eligible_buy_tickers=set()
        )

        self.assertEqual(sells, [])
        self.assertEqual(buys, [])
        self.assertEqual(portfolio.positions["TEST"].quantity, 10)

    def test_legacy_position_can_still_use_verified_price_take_profit(self):
        portfolio = VirtualPortfolio(initial_balance=10_000, commission_rate=0.0)
        portfolio.positions["TEST"] = VirtualPosition("TEST", 10, 100.0)

        sells, buys = PaperExecutor().execute(
            portfolio, self._scan("MORNING", "MOEX"), eligible_buy_tickers=set()
        )

        self.assertEqual(len(sells), 1)
        self.assertEqual(sells[0].ticker, "TEST")
        self.assertEqual(sells[0].price, 110.0)
        self.assertEqual(buys, [])
        self.assertNotIn("TEST", portfolio.positions)


if __name__ == "__main__":
    unittest.main()
