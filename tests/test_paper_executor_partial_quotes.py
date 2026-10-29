import unittest
from datetime import datetime, timezone

from bot.live_runner import LiveScanResult
from bot.paper_executor import PaperExecutor
from bot.virtual_portfolio import VirtualPortfolio


class PaperExecutorPartialQuoteTests(unittest.TestCase):
    def test_missing_quote_for_held_position_does_not_abort_cycle(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("HELD", 2, 100, datetime.now(timezone.utc))
        before_cash = portfolio.cash
        before_trades = len(portfolio.trades)

        scan = LiveScanResult(
            selected_10=[],
            selected_3=[],
            buy_candidates=[],
            analyses={},
            current_prices={},
            previous_closes={},
            lot_sizes={},
            active_trading_tickers={"CANDIDATE"},
        )

        sells, buys = PaperExecutor().execute(
            portfolio,
            scan,
            eligible_buy_tickers=set(),
        )

        self.assertEqual(sells, [])
        self.assertEqual(buys, [])
        self.assertEqual(portfolio.cash, before_cash)
        self.assertEqual(len(portfolio.trades), before_trades)
        self.assertEqual(portfolio.positions["HELD"].quantity, 2)

    def test_held_position_is_not_sold_when_not_confirmed_active(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("HELD", 2, 100, datetime.now(timezone.utc))
        before_cash = portfolio.cash
        before_trades = len(portfolio.trades)

        scan = LiveScanResult(
            selected_10=[],
            selected_3=[],
            buy_candidates=[],
            analyses={},
            current_prices={"HELD": 120.0},
            previous_closes={},
            lot_sizes={"HELD": 1},
            active_trading_tickers={"OTHER"},
        )

        sells, buys = PaperExecutor().execute(
            portfolio,
            scan,
            eligible_buy_tickers=set(),
        )

        self.assertEqual(sells, [])
        self.assertEqual(buys, [])
        self.assertEqual(portfolio.cash, before_cash)
        self.assertEqual(len(portfolio.trades), before_trades)
        self.assertEqual(portfolio.positions["HELD"].quantity, 2)

    def test_held_position_can_be_evaluated_when_confirmed_active(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("HELD", 2, 100, datetime.now(timezone.utc))

        scan = LiveScanResult(
            selected_10=[],
            selected_3=[],
            buy_candidates=[],
            analyses={},
            current_prices={"HELD": 120.0},
            previous_closes={},
            lot_sizes={"HELD": 1},
            active_trading_tickers={"HELD"},
        )

        sells, buys = PaperExecutor().execute(
            portfolio,
            scan,
            eligible_buy_tickers=set(),
        )

        self.assertEqual(len(sells), 1)
        self.assertEqual(buys, [])
        self.assertNotIn("HELD", portfolio.positions)


if __name__ == "__main__":
    unittest.main()
