import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from bot.position_manager import PositionManager
from bot.virtual_portfolio import VirtualPortfolio


class TestPositionManager(unittest.TestCase):
    def test_holds_position_when_quote_is_missing_or_invalid(self):
        invalid_quotes = (
            None,
            True,
            False,
            0,
            -1,
            float("nan"),
            float("inf"),
            float("-inf"),
        )
        negative_analysis = SimpleNamespace(
            ticker="AAA",
            momentum=-0.03,
            trend_strength=-0.01,
        )

        for price in invalid_quotes:
            with self.subTest(price=price):
                portfolio = VirtualPortfolio(10_000)
                portfolio.buy("AAA", 10, 100, datetime.now(timezone.utc))
                prices = {} if price is None else {"AAA": price}

                decisions = PositionManager().evaluate(
                    portfolio,
                    {"AAA": negative_analysis},
                    prices,
                )

                self.assertEqual(decisions[0].action, "HOLD")
                self.assertIn("валидной цены", decisions[0].reason)
                trades = PositionManager().execute_sales(portfolio, decisions, prices)
                self.assertEqual(trades, [])
                self.assertEqual(portfolio.positions["AAA"].quantity, 10)
                self.assertEqual(len(portfolio.trades), 1)

    def test_holds_profitable_position_without_sell_signal(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("AAA", 10, 100, datetime.now(timezone.utc))

        analysis = SimpleNamespace(
            ticker="AAA",
            momentum=0.03,
            trend_strength=0.01,
        )

        decisions = PositionManager().evaluate(
            portfolio,
            {"AAA": analysis},
            {"AAA": 100.14},
        )

        self.assertEqual(decisions[0].action, "HOLD")

    def test_sells_when_take_profit_is_reached(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("AAA", 10, 100, datetime.now(timezone.utc))

        analysis = SimpleNamespace(
            ticker="AAA",
            momentum=0.03,
            trend_strength=0.01,
        )

        decisions = PositionManager().evaluate(
            portfolio,
            {"AAA": analysis},
            {"AAA": 100.26},
        )

        self.assertEqual(decisions[0].action, "SELL")
        self.assertIn("Take Profit", decisions[0].reason)

    def test_holds_just_below_take_profit(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("AAA", 10, 100, datetime.now(timezone.utc))

        analysis = SimpleNamespace(
            ticker="AAA",
            momentum=0.03,
            trend_strength=0.01,
        )

        decisions = PositionManager().evaluate(
            portfolio,
            {"AAA": analysis},
            {"AAA": 100.149},
        )

        self.assertEqual(decisions[0].action, "HOLD")

    def test_take_profit_works_without_fresh_analysis(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("AAA", 10, 100, datetime.now(timezone.utc))

        decisions = PositionManager().evaluate(
            portfolio,
            {},
            {"AAA": 100.26},
        )

        self.assertEqual(decisions[0].action, "SELL")
        self.assertIn("Take Profit", decisions[0].reason)

    def test_sells_when_stop_loss_is_reached(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("AAA", 10, 100, datetime.now(timezone.utc))

        analysis = SimpleNamespace(
            ticker="AAA",
            momentum=0.0,
            trend_strength=0.01,
        )

        decisions = PositionManager().evaluate(
            portfolio,
            {"AAA": analysis},
            {"AAA": 94},
        )

        self.assertEqual(decisions[0].action, "SELL")

    def test_sells_at_exact_effective_stop_loss_after_commission(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("AAA", 10, 100, datetime.now(timezone.utc))

        analysis = SimpleNamespace(
            ticker="AAA",
            momentum=0.0,
            trend_strength=0.01,
        )

        decisions = PositionManager().evaluate(
            portfolio,
            {"AAA": analysis},
            {"AAA": 95.095},
        )

        self.assertEqual(decisions[0].action, "SELL")

    def test_holds_just_above_effective_stop_loss_after_commission(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("AAA", 10, 100, datetime.now(timezone.utc))

        analysis = SimpleNamespace(
            ticker="AAA",
            momentum=0.0,
            trend_strength=0.01,
        )

        decisions = PositionManager().evaluate(
            portfolio,
            {"AAA": analysis},
            {"AAA": 95.099},
        )

        self.assertEqual(decisions[0].action, "HOLD")

    def test_sells_on_negative_momentum_and_trend(self):
        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("AAA", 10, 100, datetime.now(timezone.utc))

        analysis = SimpleNamespace(
            ticker="AAA",
            momentum=-0.03,
            trend_strength=-0.01,
        )

        decisions = PositionManager().evaluate(
            portfolio,
            {"AAA": analysis},
            {"AAA": 100},
        )

        self.assertEqual(decisions[0].action, "SELL")


if __name__ == "__main__":
    unittest.main()
