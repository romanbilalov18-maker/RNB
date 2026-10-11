import unittest
from types import SimpleNamespace
from datetime import datetime, timezone

from bot.intelligence.decision_engine import DecisionEngine
from bot.paper_executor import PaperExecutor
from bot.stock_analysis import StockAnalysis
from bot.virtual_portfolio import VirtualPortfolio


def make_analysis(ticker, volatility=0.02):
    return StockAnalysis(
        instrument_id=ticker,
        ticker=ticker,
        last_price=10.0,
        return_period=0.05,
        volatility=volatility,
        momentum=0.03,
        average_volume=1000.0,
        volume_ratio=1.2,
        trend_strength=0.01,
        score=0.8,
    )


def make_intelligence(score, confidence=0.8, consistency=0.8):
    return SimpleNamespace(
        overall_score=score,
        overall_confidence=confidence,
        overall_consistency=consistency,
    )


class IntelligencePaperExecutionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.aaa = make_analysis("AAA")
        self.bbb = make_analysis("BBB", volatility=0.03)
        self.scan = SimpleNamespace(
            analyses={"AAA": self.aaa, "BBB": self.bbb},
            buy_candidates=[self.aaa, self.bbb],
            current_prices={"AAA": 10.0, "BBB": 20.0},
            lot_sizes={"AAA": 1, "BBB": 1},
        )
        self.portfolio = VirtualPortfolio(initial_balance=1000.0, commission_rate=0.001)

    def run_cycle(self, results):
        decisions = DecisionEngine().evaluate(
            results, held_tickers=set(self.portfolio.positions)
        )
        allowed = {
            ticker for ticker, decision in decisions.items()
            if decision.action == "BUY"
        }
        sells, buys = PaperExecutor(max_position_weight=0.35).execute(
            self.portfolio, self.scan, eligible_buy_tickers=allowed
        )
        return decisions, sells, buys

    def test_buy_requires_intelligence_buy_recommendation(self):
        decisions, sells, buys = self.run_cycle({
            "AAA": make_intelligence(0.80),
            "BBB": make_intelligence(0.40),
        })
        self.assertEqual(decisions["AAA"].action, "BUY")
        self.assertEqual(decisions["BBB"].action, "WAIT")
        self.assertEqual({trade.ticker for trade in buys}, {"AAA"})
        self.assertEqual(sells, [])
        self.assertIn("AAA", self.portfolio.positions)
        self.assertNotIn("BBB", self.portfolio.positions)

    def test_missing_intelligence_result_blocks_that_candidate(self):
        _, _, buys = self.run_cycle({"AAA": make_intelligence(0.80)})
        self.assertEqual({trade.ticker for trade in buys}, {"AAA"})
        self.assertNotIn("BBB", self.portfolio.positions)

    def test_no_buy_recommendations_means_no_new_positions(self):
        _, sells, buys = self.run_cycle({
            "AAA": make_intelligence(0.40),
            "BBB": make_intelligence(0.40),
        })
        self.assertEqual(sells, [])
        self.assertEqual(buys, [])
        self.assertEqual(self.portfolio.positions, {})
        self.assertEqual(self.portfolio.trades, [])

    def test_existing_take_profit_exit_works_when_buy_allowlist_empty(self):
        self.portfolio.buy("AAA", 10, 100.0, datetime.now(timezone.utc))
        self.scan.analyses = {"AAA": self.aaa}
        self.scan.buy_candidates = [self.aaa]
        self.scan.current_prices = {"AAA": 102.0}
        self.scan.lot_sizes = {"AAA": 1}

        sells, buys = PaperExecutor(take_profit=0.0015).execute(
            self.portfolio, self.scan, eligible_buy_tickers=set()
        )
        self.assertEqual(len(sells), 1)
        self.assertEqual(sells[0].side, "SELL")
        self.assertEqual(buys, [])
        self.assertNotIn("AAA", self.portfolio.positions)


if __name__ == "__main__":
    unittest.main()
