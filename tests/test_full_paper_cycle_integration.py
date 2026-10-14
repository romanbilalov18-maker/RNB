import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from bot.decision_audit import DecisionAuditStore
from bot.intelligence.decision_engine import DecisionEngine
from bot.intelligence.integration import analyze_scan
from bot.paper_executor import PaperExecutor
from bot.portfolio_store import SQLitePortfolioStore
from bot.stock_analysis import StockAnalysis


class DeterministicPipeline:
    """Full-cycle test double for the expensive L1-L15 calculation boundary."""

    def analyze(self, snapshot):
        score = 0.82 if snapshot.symbol == "AAA" else 0.35
        return SimpleNamespace(
            symbol=snapshot.symbol,
            overall_score=score,
            overall_confidence=0.85,
            overall_consistency=0.82,
            warnings=(),
            **{
                f"level_{number:02d}": SimpleNamespace(
                    score=score,
                    confidence=0.85,
                    analyzer_results=(),
                    metadata={},
                )
                for number in range(1, 16)
            },
        )


def make_analysis(ticker, score=0.8):
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


def candle(day, close):
    return SimpleNamespace(
        time=datetime.fromisoformat(day).replace(tzinfo=timezone.utc),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000,
    )


class FullPaperCycleIntegrationTests(unittest.TestCase):
    def test_market_scan_decision_virtual_trade_persistence_and_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = datetime.now(timezone.utc)
            yesterday = (now.date() - timedelta(days=2)).isoformat()
            prior = (now.date() - timedelta(days=3)).isoformat()
            aaa = make_analysis("AAA")
            bbb = make_analysis("BBB", score=0.4)
            history = {
                "AAA": [candle(prior, 9.8), candle(yesterday, 9.9)],
                "BBB": [candle(prior, 20.0), candle(yesterday, 20.0)],
            }
            scan = SimpleNamespace(
                analyses={"AAA": aaa, "BBB": bbb},
                buy_candidates=[aaa, bbb],
                current_prices={"AAA": 10.0, "BBB": 20.0},
                previous_closes={"AAA": 9.8, "BBB": 20.0},
                lot_sizes={"AAA": 1, "BBB": 1},
                latest_candles={"AAA": history["AAA"][-1], "BBB": history["BBB"][-1]},
                candle_history=history,
                market_return=0.01,
                market_breadth=0.7,
                market_sample_count=2,
                sector_by_ticker={"AAA": "TECH", "BBB": "TECH"},
                sector_returns={"TECH": 0.01},
            )

            portfolio_store = SQLitePortfolioStore(Path(tmp) / "portfolio.sqlite")
            audit_store = DecisionAuditStore(Path(tmp) / "audit.sqlite")
            portfolio = portfolio_store.load_or_create(1000.0, 0.001)

            # Run scan integration, real DecisionEngine, and only virtual execution.
            intelligence = analyze_scan(scan, pipeline=DeterministicPipeline(), portfolio=portfolio)
            self.assertEqual(set(intelligence), {"AAA", "BBB"})
            decisions = DecisionEngine().evaluate(intelligence, held_tickers=set(portfolio.positions))
            self.assertEqual(decisions["AAA"].action, "BUY")
            self.assertEqual(decisions["BBB"].action, "WAIT")

            allowed = {ticker for ticker, decision in decisions.items() if decision.action == "BUY"}
            reasons = {ticker: decision.reason for ticker, decision in decisions.items() if decision.action == "BUY"}
            sells, buys = PaperExecutor(max_position_weight=0.35).execute(
                portfolio, scan, eligible_buy_tickers=allowed, eligible_buy_reasons=reasons
            )
            self.assertEqual(sells, [])
            self.assertEqual({trade.ticker for trade in buys}, {"AAA"})
            self.assertNotIn("BBB", portfolio.positions)

            equity = portfolio.equity(scan.current_prices)
            portfolio_store.save(portfolio, scan.current_prices)
            audit_count = audit_store.record_cycle(
                "cycle-1",
                decisions,
                [*sells, *buys],
                equity=equity,
                cash=portfolio.cash,
                total_commissions=portfolio.commissions,
                current_prices=scan.current_prices,
                candle_history=history,
                intelligence_results=intelligence,
                commission_rate=portfolio.commission_rate,
                as_of=now,
            )
            self.assertEqual(audit_count, 2)
            summary = audit_store.summary()
            self.assertEqual(summary["observations"], 2)
            self.assertEqual(summary["observations_with_trades"], 1)
            self.assertEqual(summary["learning_observations"], 0)
            self.assertEqual(len(audit_store.learning_observations_by_ticker()), 0)

            restored = portfolio_store.load_or_create(5000.0, 0.005)
            self.assertEqual(restored.initial_balance, 1000.0)
            self.assertEqual(restored.positions, portfolio.positions)
            self.assertEqual(restored.trades, portfolio.trades)
            self.assertAlmostEqual(restored.equity(scan.current_prices), equity)

    def test_invalid_intelligence_cannot_authorize_virtual_buy(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_analysis("AAA")
            scan = SimpleNamespace(
                analyses={"AAA": candidate},
                buy_candidates=[candidate],
                current_prices={"AAA": 10.0},
                previous_closes={"AAA": 9.8},
                lot_sizes={"AAA": 1},
                latest_candles={},
                candle_history={},
            )
            portfolio_store = SQLitePortfolioStore(Path(tmp) / "portfolio.sqlite")
            portfolio = portfolio_store.load_or_create(1000.0, 0.001)
            invalid_pipeline = SimpleNamespace(
                analyze=lambda snapshot: SimpleNamespace(
                    overall_score=float("nan"),
                    overall_confidence=0.9,
                    overall_consistency=0.9,
                )
            )
            intelligence = analyze_scan(scan, pipeline=invalid_pipeline, portfolio=portfolio)
            decisions = DecisionEngine().evaluate(intelligence, held_tickers=set())
            allowed = {ticker for ticker, decision in decisions.items() if decision.action == "BUY"}
            _, buys = PaperExecutor().execute(portfolio, scan, eligible_buy_tickers=allowed)
            self.assertEqual(allowed, set())
            self.assertEqual(buys, [])
            self.assertEqual(portfolio.positions, {})
            self.assertEqual(portfolio.trades, [])


if __name__ == "__main__":
    unittest.main()
