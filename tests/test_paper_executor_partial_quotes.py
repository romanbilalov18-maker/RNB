import unittest
from contextlib import redirect_stdout
from io import StringIO
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


    def test_fresh_bid_fallback_can_exit_without_last_trade_eligibility(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("HELD", 2, 100, datetime.now(timezone.utc))

        scan = LiveScanResult(
            selected_10=[],
            selected_3=[],
            buy_candidates=[],
            analyses={},
            current_prices={"HELD": 120.0},
            previous_closes={},
            lot_sizes={},
            active_trading_tickers={"OTHER"},
            sellable_quote_tickers={"HELD"},
        )

        sells, buys = PaperExecutor().execute(
            portfolio,
            scan,
            eligible_buy_tickers=set(),
        )

        self.assertEqual(len(sells), 1)
        self.assertEqual(sells[0].ticker, "HELD")
        self.assertEqual(sells[0].price, 120.0)
        self.assertEqual(buys, [])
        self.assertNotIn("HELD", portfolio.positions)

    def test_fresh_bid_fallback_triggers_existing_stop_loss_rule(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("HELD", 2, 100, datetime.now(timezone.utc))

        scan = LiveScanResult(
            selected_10=[],
            selected_3=[],
            buy_candidates=[],
            analyses={},
            current_prices={"HELD": 94.0},
            previous_closes={},
            lot_sizes={},
            active_trading_tickers={"OTHER"},
            sellable_quote_tickers={"HELD"},
            candle_history={"HELD": []},
        )

        sells, buys = PaperExecutor().execute(
            portfolio,
            scan,
            eligible_buy_tickers=set(),
        )

        self.assertEqual(len(sells), 1)
        self.assertEqual(sells[0].ticker, "HELD")
        self.assertEqual(sells[0].price, 94.0)
        self.assertIn("лимит убытка -5%", sells[0].reason)
        self.assertEqual(buys, [])
        self.assertNotIn("HELD", portfolio.positions)

    def test_fresh_bid_fallback_does_not_sell_without_an_exit_signal(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("HELD", 2, 100, datetime.now(timezone.utc))

        scan = LiveScanResult(
            selected_10=[],
            selected_3=[],
            buy_candidates=[],
            analyses={},
            current_prices={"HELD": 100.0},
            previous_closes={},
            lot_sizes={},
            active_trading_tickers={"OTHER"},
            sellable_quote_tickers={"HELD"},
            candle_history={"HELD": []},
        )

        sells, buys = PaperExecutor().execute(
            portfolio,
            scan,
            eligible_buy_tickers=set(),
        )

        self.assertEqual(sells, [])
        self.assertEqual(buys, [])
        self.assertIn("HELD", portfolio.positions)
        self.assertEqual(portfolio.positions["HELD"].quantity, 2)

    def test_stale_or_missing_exit_price_never_invents_a_sale(self):
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
            active_trading_tickers={"OTHER"},
            sellable_quote_tickers=set(),
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
        self.assertIn("HELD", portfolio.positions)

    def test_position_is_not_managed_in_a_different_named_session(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("HELD", 2, 100, datetime.now(timezone.utc))
        portfolio.positions["HELD"].purchase_session = "previous_session"
        portfolio.positions["HELD"].purchase_exchange = "MOEX"

        scan = LiveScanResult(
            selected_10=[],
            selected_3=[],
            buy_candidates=[],
            analyses={},
            current_prices={"HELD": 120.0},
            previous_closes={},
            lot_sizes={"HELD": 1},
            active_trading_tickers={"HELD"},
            session_by_ticker={
                "HELD": {
                    "session": "current_session",
                    "instrument_exchange": "MOEX",
                }
            },
        )

        sells, buys = PaperExecutor().execute(
            portfolio,
            scan,
            eligible_buy_tickers=set(),
        )

        self.assertEqual(sells, [])
        self.assertEqual(buys, [])
        self.assertEqual(portfolio.positions["HELD"].quantity, 2)


    def test_sell_decision_and_execution_are_separately_audited(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("HELD", 2, 100, datetime.now(timezone.utc))
        scan = LiveScanResult(
            selected_10=[], selected_3=[], buy_candidates=[], analyses={},
            current_prices={"HELD": 94.0}, previous_closes={}, lot_sizes={},
            active_trading_tickers={"HELD"},
        )
        output = StringIO()
        with redirect_stdout(output):
            sells, buys = PaperExecutor().execute(
                portfolio, scan, eligible_buy_tickers=set()
            )
        log = output.getvalue()
        self.assertEqual(len(sells), 1)
        self.assertEqual(buys, [])
        self.assertIn("SELL_DECISION: ticker=HELD", log)
        self.assertIn("SELL_EXECUTED: ticker=HELD", log)
        self.assertNotIn("SELL_SKIPPED: ticker=HELD", log)


if __name__ == "__main__":
    unittest.main()
