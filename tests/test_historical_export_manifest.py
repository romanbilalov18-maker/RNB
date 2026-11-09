"""Regression tests for the historical export dataset manifest."""
import unittest

from bot.intelligence.levels.level_01.export_historical_data import build_coverage_registry, build_manifest


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

    def test_coverage_registry_keeps_catalog_entries_without_received_candles(self):
        class Instrument:
            def __init__(self, ticker, uid, first_daily=None, delisted=None):
                self.ticker = ticker
                self.uid = uid
                self.first_1day_candle_date = first_daily
                self.delisted_date = delisted
                self.buy_available_flag = False

        registry = build_coverage_registry(
            [
                Instrument("AAA", "uid-a", "2020-01-01"),
                Instrument("BBB", "uid-b", "2018-04-02", "2024-09-01"),
            ],
            {"AAA": [object(), object()]},
            "2026-11-08T00:00:00+00:00",
        )

        self.assertEqual(registry["registry_type"], "current_catalog_and_observed_candle_coverage")
        self.assertFalse(registry["historical_universe_reconstructed"])
        self.assertEqual(registry["catalog_instrument_count"], 2)
        self.assertEqual(registry["instruments_with_received_daily_candles"], 1)
        self.assertEqual(registry["instruments_without_received_daily_candles"], 1)
        records = {row["ticker"]: row for row in registry["instrument_records"]}
        self.assertEqual(records["AAA"]["daily_candle_rows"], 2)
        self.assertEqual(records["AAA"]["daily_candle_export_status"], "received")
        self.assertEqual(records["BBB"]["daily_candle_rows"], 0)
        self.assertEqual(records["BBB"]["daily_candle_export_status"], "not_received_or_not_requested")
        self.assertEqual(records["BBB"]["delisted_date"], "2024-09-01")
        self.assertTrue(any("does not prove" in limitation for limitation in registry["limitations"]))

    def test_coverage_registry_handles_empty_candle_map_without_fabrication(self):
        class Instrument:
            ticker = "AAA"
            uid = "uid-a"

        registry = build_coverage_registry([Instrument()], {}, "2026-11-08")
        self.assertEqual(registry["instruments_without_received_daily_candles"], 1)
        self.assertEqual(registry["instrument_records"][0]["daily_candle_rows"], 0)

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
