import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bot.intelligence.levels.level_12.historical_anomaly_backtest import evaluate_level12_anomaly_history


def make_candles(closes):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        SimpleNamespace(
            time=start + timedelta(days=i),
            open=close * 0.997,
            high=close * 1.015,
            low=close * 0.985,
            close=close,
            volume=1000 + (i % 7) * 100,
        )
        for i, close in enumerate(closes)
    ]


class HistoricalLevel12AnomalyBacktestTests(unittest.TestCase):
    def test_reports_anomaly_scores_against_future_adverse_events(self):
        closes = [100.0]
        for i in range(1, 100):
            closes.append(closes[-1] * (1.012 if i % 5 in (0, 1, 2) else 0.988))
        report = evaluate_level12_anomaly_history(
            make_candles(closes), symbol="TEST", horizons=(1, 3, 5),
        )
        self.assertFalse(report["methodology"]["lookahead"])
        self.assertTrue(report["methodology"]["snapshot_uses_past_only"])
        self.assertTrue(report["outcomes"])
        self.assertEqual(set(report["summary"]), {"h1", "h3", "h5"})
        for item in report["outcomes"]:
            self.assertGreaterEqual(item["anomaly_score"], 0.0)
            self.assertLessEqual(item["anomaly_score"], 1.0)
            self.assertGreaterEqual(item["realized_adverse_move"], 0.0)
            self.assertIsInstance(item["adverse_event"], bool)
        for summary in report["summary"].values():
            self.assertIn("precision", summary["threshold_metrics"])
            self.assertIn("top_quartile_event_rate_lift", summary)

    def test_future_changes_do_not_change_past_anomaly_scores(self):
        closes = [100.0]
        for i in range(1, 80):
            closes.append(closes[-1] * (1.01 if i % 4 in (0, 1) else 0.99))
        original = make_candles(closes)
        changed = make_candles(closes)
        cutoff = 50
        for i in range(cutoff + 1, len(changed)):
            value = changed[i].close * (1.10 if i % 2 else 0.90)
            changed[i] = SimpleNamespace(
                time=changed[i].time, open=value * 0.997, high=value * 1.015,
                low=value * 0.985, close=value, volume=changed[i].volume,
            )
        before = evaluate_level12_anomaly_history(original, symbol="TEST", horizons=(1, 3, 5))
        after = evaluate_level12_anomaly_history(changed, symbol="TEST", horizons=(1, 3, 5))
        cutoff_date = original[cutoff].time.isoformat()
        def past_scores(report):
            return [
                (item["signal_date"], item["horizon"], item["anomaly_score"],
                 item["anomaly_confidence"], item["price_anomaly"], item["volume_anomaly"],
                 item["volatility_anomaly"], item["behavior_anomaly"], item["signal_anomaly"],
                 item["data_anomaly"])
                for item in report["outcomes"] if item["signal_date"] <= cutoff_date
            ]
        self.assertEqual(past_scores(before), past_scores(after))

    def test_insufficient_history_returns_explicit_warning(self):
        report = evaluate_level12_anomaly_history(
            make_candles([100.0, 101.0, 102.0]), horizons=(1, 3, 5),
        )
        self.assertEqual(report["outcomes"], [])
        self.assertIn("level12_anomaly_history_insufficient", report["warnings"])

    def test_rejects_invalid_thresholds_and_horizons(self):
        candles = make_candles([100.0 + i for i in range(40)])
        with self.assertRaises(ValueError):
            evaluate_level12_anomaly_history(candles, horizons=(0,))
        with self.assertRaises(ValueError):
            evaluate_level12_anomaly_history(candles, adverse_move_threshold=1.0)
        with self.assertRaises(ValueError):
            evaluate_level12_anomaly_history(candles, anomaly_score_threshold=-0.1)


if __name__ == "__main__":
    unittest.main()
