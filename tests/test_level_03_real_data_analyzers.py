import unittest

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_03.analyzers import correlation_context, macro_context, sector_context
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


def _level2():
    return Level2Result(
        symbol="TEST", score=0.5, confidence=0.5, consistency=0.5,
        analyzer_results=(), warnings=(), metadata={},
    )


class Level03RealDataAnalyzerTests(unittest.TestCase):
    def test_sector_context_requires_observed_market_benchmark(self):
        snapshot = MarketSnapshot(
            symbol="TEST", price=100, sector="technology",
            sector_return=0.02, market_return=None, peer_count=5,
        )
        result = sector_context.analyze(snapshot, _level2())
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("sector_relative_context_unavailable", result.warnings)

    def test_sector_context_uses_relative_return(self):
        snapshot = MarketSnapshot(
            symbol="TEST", price=100, sector="technology",
            sector_return=0.02, market_return=0.01, peer_count=5,
        )
        result = sector_context.analyze(snapshot, _level2())
        self.assertAlmostEqual(result.metrics["relative_return"], 0.01)
        self.assertEqual(result.metrics["benchmark_source"], "observed_market_return")

    def test_macro_context_rejects_invalid_breadth(self):
        for breadth in (float("nan"), float("inf"), -0.1, 1.1, True):
            with self.subTest(breadth=breadth):
                result = macro_context.analyze(
                    MarketSnapshot(symbol="TEST", price=100, market_breadth=breadth, market_sample_count=20),
                    _level2(),
                )
                self.assertEqual(result.confidence, 0.0)

    def test_correlation_excludes_non_finite_pairs(self):
        left = tuple(float(i) for i in range(12))
        right = tuple(float(i) for i in range(12))
        left = left[:5] + (float("nan"),) + left[6:]
        result = correlation_context.analyze(
            MarketSnapshot(
                symbol="TEST", price=100,
                correlation_asset_returns=left,
                market_return_history=right,
                correlation_benchmark="official_index",
            ),
            _level2(),
        )
        self.assertEqual(result.metrics["observations"], 11)
        self.assertIn("correlation_invalid_or_unpaired_observations_excluded", result.warnings)


if __name__ == "__main__":
    unittest.main()
