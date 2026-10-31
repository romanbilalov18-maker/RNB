import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from bot.intelligence.decision_engine import DecisionEngine
from bot.intelligence.integration import analyze_scan
from bot.paper_executor import PaperExecutor
from bot.portfolio_store import SQLitePortfolioStore
from bot.stock_analysis import StockAnalysis
from bot.virtual_portfolio import VirtualPortfolio


class FixedPipeline:
    """Deterministic Intelligence boundary for testing the end-to-end wiring."""

    def analyze(self, snapshot):
        return SimpleNamespace(
            symbol=snapshot.symbol,
            overall_score=0.80 if snapshot.symbol == "AAA" else 0.40,
            overall_confidence=0.80,
            overall_consistency=0.80,
        )


def analysis(ticker: str, score: float = 0.8) -> StockAnalysis:
    return StockAnalysis(
        instrument_id=ticker,
        ticker=ticker,
        last_price=10.0,
        return_period=0.05,
        volatility=0.02,
        momentum=0.03,
        average_volume=1000.0,
        volume_ratio=1.2,
        trend_strength=0.01,
        score=score,
    )


class PaperCyclePersistenceTests(unittest.TestCase):
    def test_scan_intelligence_decision_paper_trade_and_restart_round_trip(self):
        candidate = analysis("AAA")
        rejected = analysis("BBB", score=0.4)
        scan = SimpleNamespace(
            analyses={"AAA": candidate, "BBB": rejected},
            buy_candidates=[candidate, rejected],
            current_prices={"AAA": 10.0, "BBB": 20.0},
            previous_closes={"AAA": 9.8, "BBB": 20.0},
            lot_sizes={"AAA": 1, "BBB": 1},
            latest_candles={},
        )

        # Exercise the real scan-to-snapshot integration and decision engine.
        intelligence = analyze_scan(scan, pipeline=FixedPipeline())
        decisions = DecisionEngine().evaluate(intelligence, held_tickers=set())
        allowed_buys = {
            ticker for ticker, decision in decisions.items()
            if decision.action == "BUY"
        }

        with tempfile.TemporaryDirectory() as directory:
            store = SQLitePortfolioStore(Path(directory) / "portfolio.sqlite3")
            portfolio = store.load_or_create(1000.0, 0.001)
            sells, buys = PaperExecutor(max_position_weight=0.35).execute(
                portfolio, scan, eligible_buy_tickers=allowed_buys
            )

            self.assertEqual(sells, [])
            self.assertGreater(len(buys), 0)
            self.assertEqual({trade.ticker for trade in buys}, {"AAA"})
            self.assertNotIn("BBB", portfolio.positions)

            equity_before_restart = portfolio.equity(scan.current_prices)
            store.save(portfolio, scan.current_prices)

            restored = store.load_or_create(5000.0, 0.005)
            self.assertEqual(restored.initial_balance, 1000.0)
            self.assertEqual(restored.commission_rate, 0.001)
            self.assertEqual(restored.cash, portfolio.cash)
            self.assertEqual(restored.positions, portfolio.positions)
            self.assertEqual(restored.trades, portfolio.trades)
            self.assertAlmostEqual(restored.equity(scan.current_prices), equity_before_restart)
            equity_history = store.equity_history()
            self.assertEqual(len(equity_history), 2)
            self.assertEqual(equity_history[0], portfolio.initial_balance)
            self.assertAlmostEqual(equity_history[1], equity_before_restart)

    def test_invalid_intelligence_result_cannot_authorize_new_virtual_buy(self):
        candidate = analysis("AAA")
        scan = SimpleNamespace(
            analyses={"AAA": candidate},
            buy_candidates=[candidate],
            current_prices={"AAA": 10.0},
            previous_closes={"AAA": 9.8},
            lot_sizes={"AAA": 1},
            latest_candles={},
        )

        intelligence = analyze_scan(scan, pipeline=SimpleNamespace(
            analyze=lambda snapshot: SimpleNamespace(
                overall_score=float("nan"),
                overall_confidence=0.9,
                overall_consistency=0.9,
            )
        ))
        decisions = DecisionEngine().evaluate(intelligence, held_tickers=set())
        allowed_buys = {
            ticker for ticker, decision in decisions.items()
            if decision.action == "BUY"
        }

        portfolio = VirtualPortfolio(initial_balance=1000.0)
        _, buys = PaperExecutor().execute(
            portfolio, scan, eligible_buy_tickers=allowed_buys
        )

        self.assertEqual(allowed_buys, set())
        self.assertEqual(buys, [])
        self.assertEqual(portfolio.positions, {})
        self.assertEqual(portfolio.trades, [])


if __name__ == "__main__":
    unittest.main()
