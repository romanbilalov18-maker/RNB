import csv
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from bot.intelligence.levels.level_01.historical_validation import (
    evaluate,
    load_rows,
    load_official_trading_dates,
)


class Level01HistoricalValidationTests(unittest.TestCase):
    def write_csv(self, rows):
        handle = tempfile.NamedTemporaryFile(mode="w", newline="", suffix=".csv", delete=False, encoding="utf-8")
        with handle:
            writer = csv.DictWriter(handle, fieldnames=["timestamp", "symbol", "close", "volume"])
            writer.writeheader()
            writer.writerows(rows)
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return Path(handle.name)

    def test_loads_real_format_and_sorts_rows(self):
        path = self.write_csv([
            {"timestamp": "2026-01-02", "symbol": "AAA", "close": 102, "volume": 100},
            {"timestamp": "2026-01-01", "symbol": "AAA", "close": 100, "volume": 90},
        ])
        rows = load_rows(path)
        self.assertEqual(rows["AAA"][0]["timestamp"], "2026-01-01")

    def test_sorts_offset_timestamps_by_instant_not_string(self):
        path = self.write_csv([
            {"timestamp": "2026-01-01T08:00:00+00:00", "symbol": "AAA", "close": 102, "volume": 100},
            {"timestamp": "2026-01-01T09:00:00+02:00", "symbol": "AAA", "close": 100, "volume": 90},
        ])
        rows = load_rows(path)
        self.assertEqual(rows["AAA"][0]["timestamp"], "2026-01-01T09:00:00+02:00")
        self.assertEqual(rows["AAA"][1]["timestamp"], "2026-01-01T08:00:00+00:00")

    def test_rejects_same_instant_with_different_timezone_offsets(self):
        path = self.write_csv([
            {"timestamp": "2026-01-01T09:00:00+02:00", "symbol": "AAA", "close": 100, "volume": 90},
            {"timestamp": "2026-01-01T07:00:00+00:00", "symbol": "AAA", "close": 101, "volume": 100},
        ])
        with self.assertRaisesRegex(ValueError, "duplicate timestamps"):
            load_rows(path)

    def test_rejects_invalid_price(self):
        path = self.write_csv([
            {"timestamp": "2026-01-01", "symbol": "AAA", "close": 0, "volume": 100},
        ])
        with self.assertRaisesRegex(ValueError, "close must be finite"):
            load_rows(path)

    def test_rejects_duplicate_timestamps(self):
        path = self.write_csv([
            {"timestamp": "2026-01-01", "symbol": "AAA", "close": 100, "volume": 100},
            {"timestamp": "2026-01-01", "symbol": "AAA", "close": 101, "volume": 100},
        ])
        with self.assertRaisesRegex(ValueError, "duplicate timestamps"):
            load_rows(path)

    def test_uses_non_overlapping_outcomes_and_chronological_holdout(self):
        rows = []
        for index in range(40):
            rows.append({
                "timestamp": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
                "symbol": "AAA",
                "close": 100.0 + index * 0.5,
                "volume": 1000 + index * 10,
            })
        path = self.write_csv(rows)
        report = evaluate(path, window=10, horizon=3)
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["evaluated_observations"], 9)
        self.assertTrue(report["non_overlapping_outcomes"])
        self.assertGreater(report["metrics"]["development_chronological"]["observations"], 0)
        self.assertGreater(report["metrics"]["holdout_chronological"]["observations"], 0)
        self.assertEqual(report["data_source"], "user_supplied_csv")
        self.assertIn("limitations", report)
        self.assertIn("price", report["analyzers"])

    def test_report_includes_export_manifest_and_its_selection_warning(self):
        rows = [
            {"timestamp": (date(2026, 1, 1) + timedelta(days=index)).isoformat(), "symbol": "AAA",
             "close": 100 + index, "volume": 1000}
            for index in range(40)
        ]
        path = self.write_csv(rows)
        manifest_path = path.with_suffix(path.suffix + ".manifest.json")
        manifest_path.write_text(
            '{"data_source":"T-Invest API","selection_method":"current scanner",'
            '"historical_universe_reconstructed":false,"symbol_count":1,'
            '"sample_start":"2026-01-01","sample_end":"2026-02-09",'
            '"limitations":["Survivorship bias may affect metrics."]}',
            encoding="utf-8",
        )
        self.addCleanup(lambda: manifest_path.unlink(missing_ok=True))

        report = evaluate(path, window=10, horizon=3)

        provenance = report["dataset_provenance"]
        self.assertEqual(provenance["status"], "provided")
        self.assertEqual(provenance["data_source"], "T-Invest API")
        self.assertFalse(provenance["historical_universe_reconstructed"])
        self.assertIn("Survivorship bias may affect metrics.", provenance["limitations"])
        self.assertEqual(report["bias_assessment"], "known_current_universe_selection_bias")
        self.assertIn("Survivorship bias may affect metrics.", report["limitations"])

    def test_report_marks_missing_manifest_as_unknown_provenance(self):
        rows = [
            {"timestamp": (date(2026, 1, 1) + timedelta(days=index)).isoformat(), "symbol": "AAA",
             "close": 100 + index, "volume": 1000}
            for index in range(40)
        ]
        path = self.write_csv(rows)

        report = evaluate(path, window=10, horizon=3)

        self.assertEqual(report["dataset_provenance"]["status"], "unknown")
        self.assertEqual(report["bias_assessment"], "unknown")
        self.assertTrue(any("manifest is missing" in warning
                            for warning in report["limitations"]))
        self.assertTrue(any("manifest is missing" in warning
                            for warning in report["dataset_provenance"]["warnings"]))

    def test_skips_outcomes_that_cross_long_data_gaps(self):
        rows = []
        dates = [
            date(2026, 1, 1) + timedelta(days=index) if index < 15
            else date(2026, 3, 1) + timedelta(days=index - 15)
            for index in range(35)
        ]
        for index, stamp in enumerate(dates):
            rows.append({
                "timestamp": stamp.isoformat(),
                "symbol": "AAA",
                "close": 100.0 + index,
                "volume": 1000 + index,
            })
        path = self.write_csv(rows)

        report = evaluate(path, window=5, horizon=2, max_gap_days=7)

        self.assertGreater(report["skipped_outcomes_due_to_data_gaps"], 0)
        self.assertEqual(report["maximum_allowed_observation_gap_days"], 7)
        self.assertLess(report["evaluated_observations"], 14)

    def test_rejects_invalid_max_gap_days(self):
        rows = [
            {"timestamp": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
             "symbol": "AAA", "close": 100 + index, "volume": 1000}
            for index in range(20)
        ]
        path = self.write_csv(rows)
        with self.assertRaisesRegex(ValueError, "max_gap_days"):
            evaluate(path, window=5, horizon=2, max_gap_days=0)

    def test_assumed_cost_reduces_net_return(self):
        rows = []
        for index in range(50):
            rows.append({
                "timestamp": f"2026-{index // 28 + 1:02d}-{index % 28 + 1:02d}",
                "symbol": "AAA",
                "close": 100.0 + index,
                "volume": 1000 + index,
            })
        path = self.write_csv(rows)
        free = evaluate(path, window=10, horizon=3, cost_bps=0)
        with_cost = evaluate(path, window=10, horizon=3, cost_bps=10)
        self.assertGreater(
            free["metrics"]["all"]["mean_net_return"],
            with_cost["metrics"]["all"]["mean_net_return"],
        )

    def test_rejects_negative_cost(self):
        path = self.write_csv([
            {"timestamp": (date(2026, 1, 1) + timedelta(days=index)).isoformat(), "symbol": "AAA",
             "close": 100 + index, "volume": 1000}
            for index in range(20)
        ])
        with self.assertRaisesRegex(ValueError, "cost_bps"):
            evaluate(path, window=5, horizon=2, cost_bps=-1)



    def test_report_includes_missing_dates_from_explicit_official_calendar(self):
        rows = [
            {"timestamp": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
             "symbol": "AAA", "close": 100 + index, "volume": 1000}
            for index in range(40)
        ]
        path = self.write_csv(rows)
        calendar_path = Path(path.parent) / "official_calendar.csv"
        with calendar_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["date"])
            writer.writeheader()
            writer.writerows({"date": (date(2026, 1, 1) + timedelta(days=index)).isoformat()}
                             for index in range(40))
        self.addCleanup(lambda: calendar_path.unlink(missing_ok=True))

        # Omit one official session in observed data; don't assume weekdays or
        # holidays. The test explicitly supplies the authoritative calendar.
        rows = [row for row in rows if row["timestamp"] != "2026-01-15"]
        path.unlink(missing_ok=True)
        path = self.write_csv(rows)
        report = evaluate(path, window=10, horizon=3, official_calendar_path=calendar_path)

        gaps = report["official_calendar_gap_diagnostics"]
        self.assertEqual(gaps["calendar_dates"], 40)
        self.assertEqual(gaps["missing_dates_by_symbol"]["AAA"], ["2026-01-15"])

    def test_official_calendar_timestamp_is_normalized_to_moscow_date(self):
        calendar_path = Path(tempfile.mktemp(suffix=".csv"))
        calendar_path.write_text(
            "date\n2026-01-05T21:30:00Z\n", encoding="utf-8"
        )
        self.addCleanup(lambda: calendar_path.unlink(missing_ok=True))

        self.assertEqual(load_official_trading_dates(calendar_path), ["2026-01-06"])

    def test_official_calendar_rejects_duplicates_after_timezone_normalization(self):
        calendar_path = Path(tempfile.mktemp(suffix=".csv"))
        calendar_path.write_text(
            "date\n2026-01-05T21:30:00Z\n2026-01-06T00:30:00+03:00\n",
            encoding="utf-8",
        )
        self.addCleanup(lambda: calendar_path.unlink(missing_ok=True))
        with self.assertRaisesRegex(ValueError, "duplicate dates"):
            load_official_trading_dates(calendar_path)

    def test_official_calendar_rejects_duplicate_dates(self):
        path = self.write_csv([
            {"timestamp": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
             "symbol": "AAA", "close": 100 + index, "volume": 1000}
            for index in range(20)
        ])
        calendar_path = Path(path.parent) / "duplicate_calendar.csv"
        calendar_path.write_text("date\n2026-01-01\n2026-01-01\n", encoding="utf-8")
        self.addCleanup(lambda: calendar_path.unlink(missing_ok=True))
        with self.assertRaisesRegex(ValueError, "duplicate dates"):
            evaluate(path, window=5, horizon=2, official_calendar_path=calendar_path)

if __name__ == "__main__":
    unittest.main()
