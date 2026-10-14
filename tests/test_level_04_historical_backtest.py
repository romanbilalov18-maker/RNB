import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bot.intelligence.levels.level_04.historical_backtest import evaluate_pressure_history


def make_candles(closes):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    for index, close in enumerate(closes):
        candles.append(SimpleNamespace(
            time=start + timedelta(days=index),
            open=close * 0.995,
            high=close * 1.02,
            low=close * 0.98,
            close=close,
            volume=1000 + (index % 5) * 250,
        ))
    return candles


class Level4HistoricalBacktestTests(unittest.TestCase):
    def test_reports_forward_horizons_and_no_lookahead_methodology(self):
        closes = [100.0]
        for index in range(1, 60):
            # Deterministic mixed trend to exercise both pressure directions.
            closes.append(closes[-1] * (1.012 if index % 4 in (0, 1) else 0.989))
        report = evaluate_pressure_history(
            make_candles(closes), symbol="TEST", horizons=(1, 3, 5),
            signal_threshold=0.55, round_trip_cost=0.001,
        )
        self.assertEqual(report["methodology"]["lookahead"], False)
        self.assertEqual(report["methodology"]["volume_baseline"], "prior candles only")
        self.assertEqual(set(report["summary"]), {
            "buy_pressure_h1", "buy_pressure_h3", "buy_pressure_h5",
            "sell_pressure_h1", "sell_pressure_h3", "sell_pressure_h5",
        })
        for outcome in report["outcomes"]:
            self.assertIn(outcome["horizon"], (1, 3, 5))
            self.assertTrue(-1.0 < outcome["forward_return"] < 1.0)
        for metric in report["summary"].values():
            if metric["count"]:
                self.assertGreaterEqual(metric["win_rate_after_costs"], 0.0)
                self.assertLessEqual(metric["win_rate_after_costs"], 1.0)
                self.assertGreaterEqual(metric["false_signal_rate"], 0.0)
                self.assertLessEqual(metric["false_signal_rate"], 1.0)

    def test_future_prices_do_not_change_historical_signal_scores(self):
        closes = [100.0]
        for index in range(1, 50):
            closes.append(closes[-1] * (1.01 if index % 3 else 0.985))
        original = make_candles(closes)
        changed = make_candles(closes)
        # Change only prices strictly after a cutoff. Signals at/before cutoff
        # must remain the same; only their forward outcome measurements may move.
        cutoff = 30
        for index in range(cutoff + 1, len(changed)):
            value = changed[index].close * 1.08
            changed[index] = SimpleNamespace(
                time=changed[index].time,
                open=value * 0.995, high=value * 1.02, low=value * 0.98,
                close=value, volume=changed[index].volume,
            )
        kwargs = dict(symbol="TEST", horizons=(1, 3, 5), signal_threshold=0.5)
        before = evaluate_pressure_history(original, **kwargs)
        after = evaluate_pressure_history(changed, **kwargs)
        signal_fields = lambda report: [
            (item["signal_date"], item["signal"], item["pressure_score"])
            for item in report["outcomes"] if item["signal_date"] <= original[cutoff].time.isoformat()
        ]
        self.assertEqual(signal_fields(before), signal_fields(after))

    def test_insufficient_history_returns_warning_without_signals(self):
        report = evaluate_pressure_history(make_candles([100.0, 101.0, 102.0]), horizons=(1, 3, 5))
        self.assertEqual(report["signals"], 0)
        self.assertIn("historical_candles_insufficient", report["warnings"])

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_pressure_history(make_candles([100.0] * 10), horizons=(0,))
        with self.assertRaises(ValueError):
            evaluate_pressure_history(make_candles([100.0] * 10), round_trip_cost=-0.1)


if __name__ == "__main__":
    unittest.main()
