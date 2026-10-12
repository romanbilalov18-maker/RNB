from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bot.live_runner import LiveMarketRunner


class _MarketData:
    def __init__(self):
        self.share = SimpleNamespace(
            uid="uid-1",
            figi="figi-1",
            ticker="AAA",
            currency="rub",
            lot=10,
            api_trade_available_flag=True,
        )
        self.candle_calls = []

    def shares(self):
        return [self.share]

    def last_prices(self, instrument_ids):
        return [SimpleNamespace(
            instrument_uid="uid-1", price=105.0, ticker="AAA"
        )]

    def close_prices(self, instrument_ids):
        return [SimpleNamespace(
            instrument_uid="uid-1", price=100.0, ticker="AAA"
        )]

    def candles(self, instrument_id, start, end):
        self.candle_calls.append((instrument_id, start, end))
        return [
            SimpleNamespace(
                close=float(100 + index),
                volume=1000,
                time=datetime(2026, 9, 1, tzinfo=timezone.utc) + timedelta(days=index),
            )
            for index in range(20)
        ]


class LiveMarketRunnerTests(unittest.TestCase):
    def test_rest_market_data_produces_live_scan_with_analysis(self):
        client = _MarketData()

        result = LiveMarketRunner(client).run()

        self.assertEqual(result.current_prices, {"AAA": 105.0})
        self.assertEqual(result.previous_closes, {"AAA": 100.0})
        self.assertEqual(result.lot_sizes, {"AAA": 10})
        self.assertEqual([analysis.ticker for analysis in result.buy_candidates], ["AAA"])
        self.assertEqual(len(result.candle_history["AAA"]), 20)
        self.assertEqual(client.candle_calls[0][0], "uid-1")
        self.assertTrue(result.analyses["AAA"].score > 0)

    def test_skips_instrument_after_candle_request_fails(self):
        class BrokenCandles(_MarketData):
            def candles(self, instrument_id, start, end):
                raise RuntimeError("temporary API outage")

        with patch("bot.live_runner.time.sleep"):
            result = LiveMarketRunner(BrokenCandles()).run()

        self.assertEqual(result.analyses, {})
        self.assertEqual(result.candle_history, {})


if __name__ == "__main__":
    unittest.main()
