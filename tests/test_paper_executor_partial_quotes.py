import unittest
from contextlib import redirect_stdout
from io import StringIO
from datetime import datetime, timedelta, timezone

from bot.live_runner import LiveScanResult
from bot.paper_executor import PaperExecutor
from bot.virtual_portfolio import VirtualPortfolio


class PaperExecutorPartialQuoteTests(unittest.TestCase):
    def test_existing_positions_reduce_remaining_portfolio_risk_budget(self):
        portfolio = VirtualPortfolio(10_000, commission_rate=0.0)
        portfolio.buy("HELD", 20, 100.0, datetime.now(timezone.utc))

        remaining_pct, open_risk, risk_cap = PaperExecutor._remaining_risk_budget(
            portfolio,
            total_equity=10_000.0,
            configured_risk_budget_pct=0.01,
            stop_loss_pct=0.05,
        )

        self.assertAlmostEqual(open_risk, 100.0)
        self.assertAlmostEqual(risk_cap, 100.0)
        self.assertAlmostEqual(remaining_pct, 0.0)

    def test_partial_open_risk_leaves_only_remaining_budget_for_new_entries(self):
        portfolio = VirtualPortfolio(10_000, commission_rate=0.0)
        portfolio.buy("HELD", 10, 100.0, datetime.now(timezone.utc))

        remaining_pct, open_risk, risk_cap = PaperExecutor._remaining_risk_budget(
            portfolio,
            total_equity=10_000.0,
            configured_risk_budget_pct=0.01,
            stop_loss_pct=0.05,
        )

        self.assertAlmostEqual(open_risk, 50.0)
        self.assertAlmostEqual(risk_cap, 100.0)
        self.assertAlmostEqual(remaining_pct, 0.005)

    def test_invalid_open_position_risk_inputs_fail_closed(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.positions["BROKEN"] = type(
            "Position", (), {"quantity": 0, "average_price": 100.0}
        )()
        with self.assertRaisesRegex(ValueError, "invalid position"):
            PaperExecutor._remaining_risk_budget(
                portfolio,
                total_equity=10_000.0,
                configured_risk_budget_pct=0.01,
                stop_loss_pct=0.05,
            )

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
        self.assertEqual(portfolio.positions["HELD"].quote_unavailable_cycles, 1)
        self.assertEqual(portfolio.positions["HELD"].last_health_status, "QUOTE_UNAVAILABLE")

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

    def test_all_holdings_report_market_closed_without_increasing_quote_gap_counter(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("HELD_A", 2, 100, datetime.now(timezone.utc))
        portfolio.buy("HELD_B", 3, 50, datetime.now(timezone.utc))
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
            active_trading_tickers=set(),
            market_closed_tickers={"HELD_A", "HELD_B"},
        )

        output = StringIO()
        with redirect_stdout(output):
            sells, buys = PaperExecutor().execute(
                portfolio,
                scan,
                eligible_buy_tickers=set(),
            )

        log = output.getvalue()
        self.assertEqual(sells, [])
        self.assertEqual(buys, [])
        self.assertIn("POSITION STATUS: ticker=HELD_A", log)
        self.assertIn("POSITION STATUS: ticker=HELD_B", log)
        self.assertIn("health=MARKET_CLOSED", log)
        self.assertIn("recommendation=WAIT_FOR_NEXT_EXCHANGE_SESSION", log)
        self.assertEqual(portfolio.cash, before_cash)
        self.assertEqual(len(portfolio.trades), before_trades)
        self.assertEqual(set(portfolio.positions), {"HELD_A", "HELD_B"})

        self.assertEqual(portfolio.positions["HELD_A"].quote_unavailable_cycles, 0)
        self.assertEqual(portfolio.positions["HELD_B"].quote_unavailable_cycles, 0)
        self.assertEqual(portfolio.positions["HELD_A"].last_health_status, "MARKET_CLOSED")

    def test_prolonged_stagnation_is_flagged_for_review_without_forced_sale(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("HELD", 2, 100, datetime.now(timezone.utc))
        scan = LiveScanResult(
            selected_10=[], selected_3=[], buy_candidates=[], analyses={},
            current_prices={"HELD": 100.0}, previous_closes={}, lot_sizes={},
            active_trading_tickers={"HELD"},
            candle_history={
                "HELD": [
                    type("Candle", (), {
                        "close": 100.0,
                        "time": datetime(2026, 1, 1, tzinfo=timezone.utc)
                        + timedelta(days=index),
                        "is_complete": True,
                    })()
                    for index in range(6)
                ]
            },
        )

        output = StringIO()
        with redirect_stdout(output):
            sells, buys = PaperExecutor().execute(
                portfolio, scan, eligible_buy_tickers=set()
            )

        self.assertEqual(sells, [])
        self.assertEqual(buys, [])
        self.assertIn("health=PROLONGED_STAGNATION", output.getvalue())
        self.assertIn("review_required=True", output.getvalue())
        self.assertIn("HELD", portfolio.positions)
        self.assertEqual(len(portfolio.trades), 1)

    def test_broker_instrument_status_is_reported_for_held_position(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("HELD", 2, 100, datetime.now(timezone.utc))
        scan = LiveScanResult(
            selected_10=[], selected_3=[], buy_candidates=[], analyses={},
            current_prices={}, previous_closes={}, lot_sizes={},
            active_trading_tickers=set(),
            instrument_status_by_ticker={
                "HELD": {
                    "resolution": "RESOLVED",
                    "trading_status": "SECURITY_TRADING_STATUS_NOT_AVAILABLE_FOR_TRADING",
                    "api_trade_available": False,
                    "sell_available": True,
                    "status_check_succeeded": True,
                }
            },
        )

        output = StringIO()
        with redirect_stdout(output):
            sells, buys = PaperExecutor().execute(
                portfolio, scan, eligible_buy_tickers=set()
            )

        log = output.getvalue()
        self.assertEqual(sells, [])
        self.assertEqual(buys, [])
        self.assertIn("broker_instrument_status=resolution=RESOLVED", log)
        self.assertIn("api_trade_available=False", log)
        self.assertIn("review_required=True", log)
        self.assertIn("health=QUOTE_UNAVAILABLE", log)
        self.assertIn("HELD", portfolio.positions)

    def test_sell_unavailable_broker_status_requires_position_review(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("HELD", 2, 100, datetime.now(timezone.utc))
        scan = LiveScanResult(
            selected_10=[], selected_3=[], buy_candidates=[], analyses={},
            current_prices={}, previous_closes={}, lot_sizes={},
            active_trading_tickers=set(),
            instrument_status_by_ticker={
                "HELD": {
                    "resolution": "RESOLVED",
                    "trading_status": "SECURITY_TRADING_STATUS_NOT_AVAILABLE_FOR_TRADING",
                    "api_trade_available": True,
                    "sell_available": False,
                    "status_check_succeeded": True,
                }
            },
        )
        output = StringIO()
        with redirect_stdout(output):
            sells, buys = PaperExecutor().execute(
                portfolio, scan, eligible_buy_tickers=set()
            )
        self.assertEqual(sells, [])
        self.assertEqual(buys, [])
        self.assertIn("sell_available=False", output.getvalue())
        self.assertIn("review_required=True", output.getvalue())
        self.assertIn("HELD", portfolio.positions)

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
            current_prices={"HELD": 100.0},
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
