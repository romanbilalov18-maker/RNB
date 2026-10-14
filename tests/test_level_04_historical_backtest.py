import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bot.intelligence.levels.level_04.historical_backtest import (
    build_market_regime_by_date,
    evaluate_pressure_history,
    evaluate_pressure_walk_forward,
)


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

    def test_walk_forward_keeps_train_outcomes_before_split_and_holdout_after(self):
        closes = [100.0]
        for index in range(1, 121):
            closes.append(closes[-1] * (1.009 if index % 5 in (0, 1, 2) else 0.991))
        candles = make_candles(closes)
        report = evaluate_pressure_walk_forward(
            candles, symbol="TEST", horizons=(1, 3, 5),
            signal_threshold=0.55, train_fraction=0.7,
        )
        split_date = report["split_date"]
        self.assertIsNotNone(split_date)
        self.assertTrue(report["methodology"]["train_outcomes_end_before_split"])
        self.assertTrue(report["methodology"]["holdout_signals_start_on_or_after_split"])
        self.assertTrue(all(item["outcome_date"] < split_date for item in report["train"]["outcomes"]))
        self.assertTrue(all(item["signal_date"] >= split_date for item in report["holdout"]["outcomes"]))
        train_keys = {(item["signal_date"], item["signal"], item["horizon"]) for item in report["train"]["outcomes"]}
        holdout_keys = {(item["signal_date"], item["signal"], item["horizon"]) for item in report["holdout"]["outcomes"]}
        self.assertTrue(train_keys.isdisjoint(holdout_keys))

    def test_market_regimes_use_only_returns_available_on_each_date(self):
        closes = [100.0]
        for index in range(1, 50):
            closes.append(closes[-1] * (1.02 if index < 25 else 0.98))
        candles = make_candles(closes)
        regimes_before = build_market_regime_by_date({"TEST": candles}, lookback=5)
        changed = list(candles)
        for index in range(35, len(changed)):
            value = changed[index].close * 1.15
            changed[index] = SimpleNamespace(
                time=changed[index].time, open=value * 0.995,
                high=value * 1.02, low=value * 0.98, close=value,
                volume=changed[index].volume,
            )
        regimes_after = build_market_regime_by_date({"TEST": changed}, lookback=5)
        cutoff_date = candles[34].time.isoformat()
        self.assertEqual(
            {day: regime for day, regime in regimes_before.items() if day <= cutoff_date},
            {day: regime for day, regime in regimes_after.items() if day <= cutoff_date},
        )

    def test_walk_forward_groups_results_by_market_regime(self):
        closes = [100.0]
        for index in range(1, 90):
            closes.append(closes[-1] * (1.01 if index % 4 in (0, 1) else 0.99))
        candles = make_candles(closes)
        regimes = {
            candle.time.isoformat(): ("BULL" if index < 45 else "BEAR")
            for index, candle in enumerate(candles)
        }
        report = evaluate_pressure_walk_forward(
            candles, symbol="TEST", horizons=(1, 3), signal_threshold=0.55,
            train_fraction=0.65, market_regime_by_date=regimes,
        )
        self.assertIn("bull", " ".join(report["train"]["summary"]).lower())
        self.assertIn("bear", " ".join(report["holdout"]["summary"]).lower())
        self.assertTrue(all(item["market_regime"] == regimes[item["signal_date"]]
                            for item in report["train"]["outcomes"] + report["holdout"]["outcomes"]))

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_pressure_history(make_candles([100.0] * 10), horizons=(0,))
        with self.assertRaises(ValueError):
            evaluate_pressure_history(make_candles([100.0] * 10), round_trip_cost=-0.1)


if __name__ == "__main__":
    unittest.main()
