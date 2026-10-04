import json
import tempfile
import unittest
from pathlib import Path

from bot.intelligence.market_monitor import _record, run_monitor


class MarketMonitorTests(unittest.TestCase):
    def test_record_contains_price_and_all_levels(self):
        class Analysis:
            ticker = "TEST"

        class Level:
            score = 0.5
            confidence = 0.7

        class Metric:
            metrics = {"change": 0.02}

        class Result:
            overall_score = 0.65
            overall_confidence = 0.7
            overall_consistency = 0.8
            warnings = ("missing macro data",)
            level_01 = Level()
            analyzer_results = (Metric(),)

        result = Result()
        result.level_01 = type("Level1", (), {"score": 0.51, "confidence": 0.71, "analyzer_results": (Metric(),)})()
        for number in range(2, 16):
            setattr(result, f"level_{number:02d}", Level())

        record = _record(Analysis(), result, 123.45, "2026-01-01T00:00:00+00:00")

        self.assertEqual(record["symbol"], "TEST")
        self.assertEqual(record["price"], 123.45)
        self.assertEqual(record["daily_change"], 0.02)
        self.assertEqual(record["intelligence"], 0.65)
        self.assertEqual(record["warnings"], ["missing macro data"])
        for number in range(1, 16):
            self.assertIn(f"level_{number:02d}_score", record)
            self.assertIn(f"level_{number:02d}_confidence", record)

    def test_monitor_appends_one_record_per_instrument(self):
        class Analysis:
            ticker = "TEST"

        class Result:
            overall_score = 0.6
            overall_confidence = 0.7
            overall_consistency = 0.8
            warnings = ()
            level_01 = type("L", (), {"score": 0.5, "confidence": 0.6, "analyzer_results": ()})()
        
        for number in range(2, 16):
            setattr(Result, f"level_{number:02d}", type("L", (), {"score": 0.5, "confidence": 0.6})())

        def fake_run(token, limit):
            return [(Analysis(), Result(), 100.0)]

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "monitor.jsonl"
            records = run_monitor(
                "token",
                duration_minutes=1,
                interval_minutes=1,
                limit=1,
                output_path=str(output),
                sleep_fn=lambda _: None,
                run_fn=fake_run,
            )

            self.assertEqual(records, 1)
            lines = output.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["symbol"], "TEST")


if __name__ == "__main__":
    unittest.main()
