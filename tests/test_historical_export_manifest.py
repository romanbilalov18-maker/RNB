"""Regression tests for the historical export dataset manifest."""
import unittest

from bot.intelligence.levels.level_01.export_historical_data import build_manifest


class HistoricalExportManifestTests(unittest.TestCase):
    def test_manifest_reports_duplicate_symbol_timestamp_rows(self):
        rows = [
            {"timestamp": "2026-01-02T00:00:00+03:00", "symbol": "AAA"},
            {"timestamp": "2026-01-02T00:00:00+03:00", "symbol": "AAA"},
            {"timestamp": "2026-01-03T00:00:00+03:00", "symbol": "AAA"},
        ]

        manifest = build_manifest(rows, 90)

        self.assertEqual(manifest["row_count"], 3)
        self.assertEqual(manifest["unique_symbol_timestamp_count"], 2)
        self.assertEqual(manifest["duplicate_symbol_timestamp_count"], 1)
        self.assertEqual(manifest["data_integrity_status"], "duplicates_detected")
        self.assertTrue(manifest["data_quality_warnings"])

    def test_manifest_describes_real_sample_and_warns_current_universe_bias(self):
        rows = [
            {"timestamp": "2026-01-02T00:00:00+03:00", "symbol": "AAA"},
            {"timestamp": "2026-01-03T00:00:00+03:00", "symbol": "AAA"},
            {"timestamp": "2026-01-01T00:00:00+03:00", "symbol": "BBB"},
        ]

        manifest = build_manifest(rows, 90)

        self.assertEqual(manifest["data_source"], "T-Invest API")
        self.assertEqual(manifest["requested_lookback_days"], 90)
        self.assertEqual(manifest["sample_start"], "2026-01-01T00:00:00+03:00")
        self.assertEqual(manifest["sample_end"], "2026-01-03T00:00:00+03:00")
        self.assertEqual(manifest["symbol_count"], 2)
        self.assertEqual(manifest["row_count"], 3)
        self.assertEqual(manifest["unique_symbol_timestamp_count"], 3)
        self.assertEqual(manifest["duplicate_symbol_timestamp_count"], 0)
        self.assertEqual(manifest["data_integrity_status"], "unique_symbol_timestamps")
        self.assertEqual(manifest["data_quality_warnings"], [])
        self.assertEqual(manifest["symbols"]["AAA"]["rows"], 2)
        self.assertFalse(manifest["historical_universe_reconstructed"])
        self.assertTrue(any("Survivorship" in warning for warning in manifest["limitations"]))
        self.assertTrue(any("not be presented as an unbiased" in warning
                            for warning in manifest["limitations"]))


if __name__ == "__main__":
    unittest.main()
