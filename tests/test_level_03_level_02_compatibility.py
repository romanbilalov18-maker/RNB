import unittest

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result
from bot.intelligence.levels.level_03.level_03_engine import analyze
from bot.intelligence.levels.level_03.models.level_03_result import Level3Result


def level2(symbol="TEST", warnings=(), confidence=0.7, consistency=0.6, metadata=None):
    return Level2Result(
        symbol=symbol,
        score=0.55,
        confidence=confidence,
        consistency=consistency,
        analyzer_results=(AnalyzerResult("signal_conflict", 0.2, 0.7),),
        warnings=warnings,
        metadata=metadata or {"signal_conflict_semantics": "score_dispersion_proxy_not_directional_conflict"},
    )


class Level03Level02CompatibilityTests(unittest.TestCase):
    def test_rejects_level2_result_for_different_symbol(self):
        with self.assertRaisesRegex(ValueError, "does not match snapshot symbol"):
            analyze(MarketSnapshot(symbol="AAA", price=100), level2(symbol="BBB"))

    def test_preserves_level2_warnings(self):
        result = analyze(
            MarketSnapshot(symbol="TEST", price=100),
            level2(warnings=("level2_input_incomplete",)),
        )
        self.assertIn("level2_input_incomplete", result.warnings)

    def test_preserves_upstream_consistency_semantics(self):
        result = analyze(
            MarketSnapshot(symbol="TEST", price=100),
            level2(consistency=0.6, metadata={"signal_conflict_semantics": "score_dispersion_proxy_not_directional_conflict"}),
        )
        self.assertEqual(result.consistency, 0.6)
        self.assertEqual(result.metadata["level2_consistency_source"], "level2.consistency")
        self.assertEqual(result.metadata["level2_consistency_semantics"], "score_dispersion_proxy_not_directional_conflict")

    def test_reports_analyzers_without_evidence(self):
        result = analyze(MarketSnapshot(symbol="TEST", price=100), level2())
        self.assertIn("analyzers_without_evidence", result.metadata)
        self.assertIn("market_regime", result.metadata["analyzers_without_evidence"])

    def test_level3_result_rejects_bool_and_non_finite_values(self):
        for value in (True, float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    Level3Result("TEST", value, 0.5, 0.5)


if __name__ == "__main__":
    unittest.main()
