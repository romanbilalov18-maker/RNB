import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from bot.position_manager import PositionManager
from bot.virtual_portfolio import VirtualPortfolio


class TestPositionManager(unittest.TestCase):
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
            {"AAA": 103},
        )

        self.assertEqual(decisions[0].action, "HOLD")

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
