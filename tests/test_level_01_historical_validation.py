import csv
import tempfile
import unittest
from pathlib import Path

from bot.intelligence.levels.level_01.historical_validation import evaluate, load_rows


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
                "timestamp": f"2026-{index // 28 + 1:02d}-{index % 28 + 1:02d}",
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
            {"timestamp": f"2026-01-{index + 1:02d}", "symbol": "AAA",
             "close": 100 + index, "volume": 1000}
            for index in range(20)
        ])
        with self.assertRaisesRegex(ValueError, "cost_bps"):
            evaluate(path, window=5, horizon=2, cost_bps=-1)


if __name__ == "__main__":
    unittest.main()
