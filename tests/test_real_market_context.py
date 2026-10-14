import unittest
from types import SimpleNamespace

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_09.analyzers import correlation_risk
from bot.intelligence.levels.level_03.analyzers import (
    correlation_context,
    macro_context,
    sector_context,
)


class RealMarketContextTests(unittest.TestCase):
    def test_macro_context_uses_observed_market_breadth_and_return(self):
        snapshot = MarketSnapshot(
            symbol="AAA",
            price=101.0,
            previous_price=100.0,
            market_return=0.01,
            market_breadth=0.7,
            market_sample_count=120,
        )
        result = macro_context.analyze(snapshot, SimpleNamespace())
        self.assertGreater(result.confidence, 0.0)
        self.assertAlmostEqual(result.metrics["market_breadth"], 0.7)
        self.assertEqual(result.metrics["sample_count"], 120)
        self.assertFalse(result.metrics["official_macro_indicators_available"])

    def test_sector_context_is_unavailable_without_real_sector_peers(self):
        snapshot = MarketSnapshot(symbol="AAA", price=101.0, sector="TECH")
        result = sector_context.analyze(snapshot, SimpleNamespace())
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("sector_data_not_available", result.warnings)

    def test_correlation_uses_observed_aligned_return_series(self):
        asset = tuple(value / 1000.0 for value in range(-15, 15))
        market = tuple(value * 2.0 for value in asset)
        snapshot = MarketSnapshot(
            symbol="AAA",
            price=101.0,
            correlation_asset_returns=asset,
            market_return_history=market,
        )
        result = correlation_context.analyze(snapshot, SimpleNamespace())
        self.assertAlmostEqual(result.metrics["pearson_correlation"], 1.0)
        self.assertGreater(result.confidence, 0.0)


    def test_portfolio_correlation_uses_actual_held_position_history(self):
        dates = tuple(f"2026-09-{day:02d}" for day in range(1, 31))
        returns = tuple(value / 10000.0 for value in range(-15, 15))
        snapshot = MarketSnapshot(
            symbol="AAA",
            price=101.0,
            historical_return_dates=dates,
            historical_returns=returns,
            portfolio_positions=(
                {
                    "symbol": "HELD",
                    "market_value": 500.0,
                    "historical_return_dates": dates,
                    "historical_returns": returns,
                },
            ),
        )
        result = correlation_risk.analyze(snapshot, SimpleNamespace(), SimpleNamespace(adverse_scenario=0.2, confidence=0.8))
        self.assertAlmostEqual(result.metrics["weighted_absolute_correlation"], 1.0)
        self.assertGreater(result.confidence, 0.0)

    def test_correlation_does_not_fabricate_result_without_history(self):
        result = correlation_context.analyze(
            MarketSnapshot(symbol="AAA", price=100.0), SimpleNamespace()
        )
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("cross_asset_history_insufficient", result.warnings)


if __name__ == "__main__":
    unittest.main()
