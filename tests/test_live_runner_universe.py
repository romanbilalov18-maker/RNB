import os
import unittest
from unittest.mock import patch

from bot.live_runner import LiveMarketRunner


class LiveMarketRunnerUniverseTests(unittest.TestCase):
    def test_verified_completed_candles_are_sorted_and_deduplicated(self):
        from datetime import datetime, timedelta, timezone
        from types import SimpleNamespace

        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        later = SimpleNamespace(time=start + timedelta(days=1), is_complete=True)
        earlier = SimpleNamespace(time=start, is_complete=True)
        duplicate = SimpleNamespace(time=start, is_complete=True)
        incomplete = SimpleNamespace(
            time=start + timedelta(days=2), is_complete=False
        )
        missing_time = SimpleNamespace(is_complete=True)

        result = LiveMarketRunner._verified_completed_candles(
            [later, incomplete, earlier, duplicate, missing_time]
        )
        self.assertEqual(result, [earlier, later])
        self.assertIs(result[0], earlier)

    def test_verified_completed_candles_reject_naive_timestamps(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace

        valid = SimpleNamespace(
            time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            is_complete=True,
        )
        naive = SimpleNamespace(
            time=datetime(2026, 1, 2),
            is_complete=True,
        )
        self.assertEqual(
            LiveMarketRunner._verified_completed_candles([valid, naive]),
            [valid],
        )

    def test_candle_history_requests_daily_tinvest_interval(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace
        from unittest.mock import Mock
        from t_tech.invest import CandleInterval

        get_candles = Mock(return_value=object())
        client = SimpleNamespace(
            market_data=SimpleNamespace(get_candles=get_candles)
        )
        runner = LiveMarketRunner(client=client)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 10, tzinfo=timezone.utc)

        response = runner._get_candles_with_retry(
            instrument_id="broker-instrument-id",
            start=start,
            end=end,
            attempts=1,
        )

        self.assertIsNotNone(response)
        get_candles.assert_called_once_with(
            instrument_id="broker-instrument-id",
            from_=start,
            to=end,
            interval=CandleInterval.CANDLE_INTERVAL_DAY,
        )

    def test_default_analysis_universe_is_wider_than_previous_ten(self):
        with patch.dict(os.environ, {}, clear=True):
            runner = LiveMarketRunner(client=object())
        self.assertEqual(runner.max_analysis_instruments, 50)

    def test_analysis_universe_can_be_configured(self):
        with patch.dict(os.environ, {"TINVEST_MAX_ANALYSIS_INSTRUMENTS": "75"}):
            runner = LiveMarketRunner(client=object())
        self.assertEqual(runner.max_analysis_instruments, 75)

    def test_analysis_universe_rejects_non_positive_values(self):
        for value in ("0", "-5", "many"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"TINVEST_MAX_ANALYSIS_INSTRUMENTS": value}
            ):
                with self.assertRaises(ValueError):
                    LiveMarketRunner(client=object())


if __name__ == "__main__":
    unittest.main()
