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

    def test_monitor_accepts_extended_intelligence_runner_tuple_and_records_universe(self):
        class Analysis:
            ticker = "XYZ"

        class Result:
            overall_score = 0.6
            overall_confidence = 0.7
            overall_consistency = 0.8
            warnings = ()
            level_01 = type("L", (), {"score": 0.5, "confidence": 0.6, "analyzer_results": ()})()

        for number in range(2, 16):
            setattr(Result, f"level_{number:02d}", type("L", (), {"score": 0.5, "confidence": 0.6})())

        def fake_run(token, limit):
            return [(Analysis(), Result(), 100.0, {"backtest": True}, {"walk_forward": True}, {}, {}, {}, {
                "scanner_shortlist_count": 50, "buy_candidate_count": 17,
                "fresh_quote_count": 43, "active_session_count": 40,
                "monitor_analyzed_count": 1, "monitor_limit": 1,
                "scope": "current scanner, monitor limit applies",
            })]

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "monitor.jsonl"
            universe = Path(directory) / "universe.jsonl"
            records = run_monitor(
                "token", duration_minutes=1, interval_minutes=1, limit=1,
                output_path=str(output), universe_output_path=str(universe),
                sleep_fn=lambda _: None, run_fn=fake_run,
            )
            self.assertEqual(records, 1)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8").splitlines()[0])["symbol"], "XYZ")
            snapshot = json.loads(universe.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(snapshot["symbols"], ["XYZ"])
            self.assertEqual(snapshot["instrument_count"], 1)
            self.assertEqual(snapshot["scanner_shortlist_count"], 50)
            self.assertEqual(snapshot["buy_candidate_count"], 17)
            self.assertEqual(snapshot["fresh_quote_count"], 43)
            self.assertEqual(snapshot["monitor_analyzed_count"], 1)
            self.assertEqual(snapshot["monitor_limit"], 1)
            self.assertIn("not the full historical market universe", snapshot["scope"])

    def test_monitor_rejects_nonfinite_or_nonpositive_price(self):
        class Analysis:
            ticker = "BAD"

        class Result:
            overall_score = 0.5
            overall_confidence = 0.5
            overall_consistency = 0.5
            warnings = ()
            level_01 = type("L", (), {"analyzer_results": ()})()

        for number in range(2, 16):
            setattr(Result, f"level_{number:02d}", type("L", (), {"score": 0.5, "confidence": 0.5})())

        for price in (float("nan"), float("inf"), 0.0, -1.0):
            with self.subTest(price=price), self.assertRaisesRegex(ValueError, "finite and positive"):
                _record(Analysis(), Result(), price, "2026-01-01T00:00:00+00:00")

    def test_nonfinite_intelligence_metrics_are_serialized_as_null(self):
        class Analysis:
            ticker = "TEST"

        class Result:
            overall_score = float("nan")
            overall_confidence = float("inf")
            overall_consistency = 0.5
            warnings = ()
            level_01 = type("L", (), {"analyzer_results": ()})()

        for number in range(2, 16):
            setattr(Result, f"level_{number:02d}", type("L", (), {"score": float("nan"), "confidence": 0.5})())

        record = _record(Analysis(), Result(), 10.0, "2026-01-01T00:00:00+00:00")
        encoded = json.dumps(record, allow_nan=False)
        decoded = json.loads(encoded)
        self.assertIsNone(decoded["intelligence"])
        self.assertIsNone(decoded["confidence"])
        self.assertIsNone(decoded["level_02_score"])

    def test_invalid_later_price_does_not_append_partial_cycle(self):
        class Analysis:
            def __init__(self, ticker):
                self.ticker = ticker

        class Result:
            overall_score = 0.5
            overall_confidence = 0.5
            overall_consistency = 0.5
            warnings = ()
            level_01 = type("L", (), {"analyzer_results": ()})()

        for number in range(2, 16):
            setattr(Result, f"level_{number:02d}", type("L", (), {"score": 0.5, "confidence": 0.5})())

        def fake_run(token, limit):
            return [(Analysis("GOOD"), Result(), 10.0), (Analysis("BAD"), Result(), float("nan"))]

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "monitor.jsonl"
            universe = Path(directory) / "universe.jsonl"
            with self.assertRaisesRegex(ValueError, "finite and positive"):
                run_monitor(
                    "token", duration_minutes=1, interval_minutes=1, limit=2,
                    output_path=str(output), universe_output_path=str(universe),
                    sleep_fn=lambda _: None, run_fn=fake_run,
                )
            self.assertFalse(output.exists())
            self.assertFalse(universe.exists())

    def test_monitor_records_empty_scan_instead_of_dropping_cycle(self):
        def fake_run(token, limit):
            return []

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "monitor.jsonl"
            universe = Path(directory) / "universe.jsonl"
            records = run_monitor(
                "token", duration_minutes=1, interval_minutes=1, limit=2,
                output_path=str(output), universe_output_path=str(universe),
                sleep_fn=lambda _: None, run_fn=fake_run,
            )
            self.assertEqual(records, 0)
            self.assertFalse(output.exists() or output.read_text(encoding="utf-8") if output.exists() else False)
            snapshot = json.loads(universe.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(snapshot["scan_status"], "no_eligible_instruments")
            self.assertEqual(snapshot["symbols"], [])
            self.assertEqual(snapshot["instrument_count"], 0)
            self.assertEqual(snapshot["monitor_analyzed_count"], 0)

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
