import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from bot.intelligence.market_monitor import run_monitor


class MarketMonitorTests(unittest.TestCase):
    def _result(self):
        level_01 = SimpleNamespace(
            analyzer_results=(SimpleNamespace(metrics={"change": 0.012}),),
            score=0.7,
            confidence=0.8,
        )
        return SimpleNamespace(
            level_01=level_01,
            overall_score=0.7,
            overall_confidence=0.8,
            overall_consistency=0.9,
            warnings=(),
        )

    def test_writes_one_valid_json_object_per_line(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "monitor.jsonl"
            records = run_monitor(
                "token",
                duration_minutes=1,
                interval_minutes=1,
                limit=1,
                output_path=str(output),
                run_fn=lambda token, limit: [
                    (SimpleNamespace(ticker="AAA"), self._result(), 10.0)
                ],
                sleep_fn=lambda seconds: self.fail("single cycle must not sleep"),
            )

            lines = output.read_text(encoding="utf-8").splitlines()
            self.assertEqual(records, 1)
            self.assertEqual(len(lines), 1)
            parsed = json.loads(lines[0])
            self.assertEqual(parsed["symbol"], "AAA")
            self.assertAlmostEqual(parsed["price_change_from_previous"], 0.012)
            self.assertEqual(parsed["daily_change"], parsed["price_change_from_previous"])

    def test_interval_accounts_for_time_spent_scanning(self):
        with tempfile.TemporaryDirectory() as directory:
            clock_values = iter((0.0, 10.0, 60.0, 70.0))
            sleeps = []

            def scan(token, limit):
                return [(SimpleNamespace(ticker="AAA"), self._result(), 10.0)]

            run_monitor(
                "token",
                duration_minutes=2,
                interval_minutes=1,
                limit=1,
                output_path=str(Path(directory) / "monitor.jsonl"),
                run_fn=scan,
                clock_fn=lambda: next(clock_values),
                sleep_fn=sleeps.append,
            )

            self.assertEqual(sleeps, [50.0])

    def test_rejects_non_positive_parameters(self):
        with self.assertRaises(ValueError):
            run_monitor("token", duration_minutes=0)


if __name__ == "__main__":
    unittest.main()
