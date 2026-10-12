from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from bot.tinvest_client import TInvestClient


class TInvestClientTests(unittest.TestCase):
    def setUp(self):
        self.client = TInvestClient("test-secret", base_url="https://api.test/rest/")

    def call_with_response(self, payload, method):
        request_holder = {"request": None}

        def open_request(request, timeout):
            request_holder["request"] = request
            self.assertEqual(timeout, 15)
            return BytesIO(json.dumps(payload).encode())

        with patch("bot.tinvest_client.urlopen", side_effect=open_request):
            result = method()
        return result, request_holder["request"]

    def test_shares_uses_official_rest_route_and_parses_instrument_fields(self):
        route = "/rest/tinkoff.public.invest.api.contract.v1.InstrumentsService/Shares"
        response = {
            "instruments": [{
                "uid": "uid-1", "figi": "figi-1", "ticker": "AAA",
                "currency": "rub", "lot": 10, "apiTradeAvailableFlag": True,
            }]
        }

        shares, request = self.call_with_response(response, self.client.shares)

        self.assertEqual(shares[0].uid, "uid-1")
        self.assertEqual(shares[0].ticker, "AAA")
        self.assertTrue(shares[0].api_trade_available_flag)
        self.assertEqual(request.full_url, f"https://api.test{route}")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
        self.assertEqual(json.loads(request.data), {"instrumentStatus": "INSTRUMENT_STATUS_BASE"})

    def test_last_prices_decodes_quotation_and_utc_timestamp(self):
        route = "/rest/tinkoff.public.invest.api.contract.v1.MarketDataService/GetLastPrices"
        response = {
            "lastPrices": [{
                "instrumentUid": "uid-1", "figi": "figi-1", "ticker": "AAA",
                "price": {"units": "123", "nano": 500000000},
                "time": "2026-10-13T10:00:00Z",
            }]
        }

        prices, request = self.call_with_response(response, lambda: self.client.last_prices(["uid-1"]))

        self.assertEqual(prices[0].price, 123.5)
        self.assertEqual(prices[0].instrument_uid, "uid-1")
        self.assertEqual(prices[0].time.isoformat(), "2026-10-13T10:00:00+00:00")
        self.assertEqual(json.loads(request.data), {"instrumentId": ["uid-1"]})

    def test_close_prices_requests_only_selected_instruments(self):
        route = "/rest/tinkoff.public.invest.api.contract.v1.MarketDataService/GetClosePrices"
        response = {"closePrices": []}

        _, request = self.call_with_response(response, lambda: self.client.close_prices(["uid-1", "uid-2"]))

        self.assertEqual(
            json.loads(request.data),
            {"instruments": [{"instrumentId": "uid-1"}, {"instrumentId": "uid-2"}]},
        )

    def test_candles_sends_utc_dates_and_parses_ohlcv(self):
        route = "/rest/tinkoff.public.invest.api.contract.v1.MarketDataService/GetCandles"
        response = {"candles": [{
            "open": {"units": "100", "nano": 0},
            "high": {"units": "105", "nano": 0},
            "low": {"units": "99", "nano": 0},
            "close": {"units": "103", "nano": 0},
            "volume": "1800", "time": "2026-10-12T00:00:00Z",
            "isComplete": True,
        }]}

        candles, request = self.call_with_response(
            response,
            lambda: self.client.candles(
                "uid-1",
                datetime(2026, 10, 1, tzinfo=timezone.utc),
                datetime(2026, 10, 13, tzinfo=timezone.utc),
            ),
        )

        self.assertEqual(candles[0].close, 103.0)
        self.assertEqual(candles[0].volume, "1800")
        self.assertTrue(candles[0].is_complete)
        body = json.loads(request.data)
        self.assertEqual(body["instrumentId"], "uid-1")
        self.assertEqual(body["interval"], "CANDLE_INTERVAL_DAY")

    def test_http_errors_report_status_without_exposing_token(self):
        route = "/rest/tinkoff.public.invest.api.contract.v1.InstrumentsService/Shares"
        def reject(request, timeout):
            raise HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                {},
                BytesIO(b'{"message":"bad test-secret credentials"}'),
            )

        with patch("bot.tinvest_client.urlopen", side_effect=reject):
            with self.assertRaisesRegex(RuntimeError, "HTTP 401") as error:
                self.client.shares()

        self.assertNotIn("test-secret", str(error.exception))


if __name__ == "__main__":
    unittest.main()
