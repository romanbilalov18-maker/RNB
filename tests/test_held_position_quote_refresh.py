import math
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bot.live_runner import LiveMarketRunner


class HeldPositionQuoteRefreshTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc)
        self.prices = {"uid-held-1": 50.0}
        self.items = {
            "uid-held-1": SimpleNamespace(
                instrument_uid="uid-held-1",
                price=50.0,
                time=self.now - timedelta(seconds=240),
            )
        }

    def merge(self, *, price, quote_time, instrument_id="uid-held-1"):
        item = SimpleNamespace(
            instrument_uid=instrument_id,
            figi="",
            price=price,
            time=quote_time,
        )
        return LiveMarketRunner._merge_fresh_newer_quote(
            item,
            last_prices=self.prices,
            last_price_items=self.items,
            now=self.now,
            max_age_seconds=300.0,
        )

    def test_accepts_newer_fresh_quote_for_held_position(self):
        accepted = self.merge(
            price=51.25,
            quote_time=self.now - timedelta(seconds=30),
        )
        self.assertTrue(accepted)
        self.assertEqual(self.prices["uid-held-1"], 51.25)
        self.assertEqual(
            self.items["uid-held-1"].time,
            self.now - timedelta(seconds=30),
        )

    def test_rejects_stale_quote_without_changing_cached_price(self):
        accepted = self.merge(
            price=51.25,
            quote_time=self.now - timedelta(seconds=301),
        )
        self.assertFalse(accepted)
        self.assertEqual(self.prices["uid-held-1"], 50.0)

    def test_rejects_older_quote_even_when_it_is_still_fresh(self):
        accepted = self.merge(
            price=49.0,
            quote_time=self.now - timedelta(seconds=250),
        )
        self.assertFalse(accepted)
        self.assertEqual(self.prices["uid-held-1"], 50.0)

    def test_rejects_equal_timestamp_duplicate(self):
        accepted = self.merge(
            price=55.0,
            quote_time=self.now - timedelta(seconds=240),
        )
        self.assertFalse(accepted)
        self.assertEqual(self.prices["uid-held-1"], 50.0)

    def test_rejects_non_finite_or_non_positive_prices(self):
        for price in (0.0, -1.0, float("nan"), float("inf")):
            with self.subTest(price=price):
                self.setUp()
                accepted = self.merge(
                    price=price,
                    quote_time=self.now - timedelta(seconds=20),
                )
                self.assertFalse(accepted)
                self.assertEqual(self.prices["uid-held-1"], 50.0)

    def test_rejects_missing_timestamp_and_future_timestamp(self):
        self.assertFalse(self.merge(price=51.0, quote_time=None))
        self.assertFalse(
            self.merge(
                price=51.0,
                quote_time=self.now + timedelta(seconds=61),
            )
        )
        self.assertEqual(self.prices["uid-held-1"], 50.0)

    def test_accepts_figi_key_when_uid_is_unavailable(self):
        item = SimpleNamespace(
            instrument_uid="",
            figi="figi-held-2",
            price=12.5,
            time=self.now - timedelta(seconds=10),
        )
        prices = {}
        items = {}
        self.assertTrue(
            LiveMarketRunner._merge_fresh_newer_quote(
                item,
                last_prices=prices,
                last_price_items=items,
                now=self.now,
                max_age_seconds=300.0,
            )
        )
        self.assertEqual(prices, {"figi-held-2": 12.5})


if __name__ == "__main__":
    unittest.main()
