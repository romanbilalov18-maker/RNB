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

    def test_rejects_quote_older_than_300_seconds(self):
        # A newer quote still must be rejected when its source timestamp is stale.
        self.items["uid-held-1"].time = self.now - timedelta(hours=3)
        accepted = self.merge(
            price=51.25,
            quote_time=self.now - timedelta(hours=2),
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

    def test_post_analysis_refresh_requests_all_analyzed_instruments(self):
        fresh_time = self.now - timedelta(seconds=20)
        stale_time = self.now - timedelta(hours=2)
        response = SimpleNamespace(last_prices=[
            SimpleNamespace(instrument_uid="uid-held-1", figi="", price=51.0, time=fresh_time),
            SimpleNamespace(instrument_uid="uid-candidate-2", figi="", price=12.0, time=stale_time),
        ])
        class FakeMarketData:
            requested = None
            def get_last_prices(self, *, instrument_id):
                self.requested = list(instrument_id)
                return response
        market_data = FakeMarketData()
        runner = LiveMarketRunner(SimpleNamespace(market_data=market_data))
        prices = {"uid-held-1": 50.0, "uid-candidate-2": 11.0}
        items = {
            "uid-held-1": SimpleNamespace(time=self.now - timedelta(seconds=240)),
            "uid-candidate-2": SimpleNamespace(time=self.now - timedelta(hours=3)),
        }
        accepted, returned = runner._refresh_latest_quotes(
            ["uid-held-1", "uid-candidate-2"],
            last_prices=prices,
            last_price_items=items,
            now=self.now,
        )
        self.assertEqual(market_data.requested, ["uid-candidate-2", "uid-held-1"])
        self.assertEqual(returned, 2)
        self.assertEqual(accepted, 1)
        self.assertEqual(prices["uid-held-1"], 51.0)
        self.assertEqual(prices["uid-candidate-2"], 11.0)

    def test_valuation_universe_includes_nontradable_held_instrument(self):
        tradable = SimpleNamespace(
            ticker="AAA", uid="uid-aaa", figi="", currency="RUB",
            api_trade_available_flag=True,
        )
        held_but_not_tradable = SimpleNamespace(
            ticker="HELD", uid="uid-held", figi="", currency="USD",
            api_trade_available_flag=False,
        )
        unrelated_not_tradable = SimpleNamespace(
            ticker="OTHER", uid="uid-other", figi="", currency="USD",
            api_trade_available_flag=False,
        )

        universe = LiveMarketRunner._valuation_universe(
            [tradable],
            [tradable, held_but_not_tradable, unrelated_not_tradable],
            {"HELD"},
        )

        self.assertEqual(
            {share.ticker for share in universe},
            {"AAA", "HELD"},
        )
        self.assertEqual(
            {share.uid for share in universe},
            {"uid-aaa", "uid-held"},
        )

    def test_resolves_missing_held_ticker_from_find_instrument(self):
        held = SimpleNamespace(
            ticker="ELMT", uid="uid-elmt", figi="", instrument_type="share",
            currency="RUB", lot=1, exchange="MOEX",
        )
        class FakeInstruments:
            def find_instrument(self, *, query):
                self.query = query
                return SimpleNamespace(instruments=[held])
        runner = LiveMarketRunner(SimpleNamespace(instruments=FakeInstruments()))
        result = runner._resolve_missing_held_shares([], {"ELMT"})
        self.assertEqual(result, [held])
        self.assertEqual(runner.client.instruments.query, "ELMT")

    def test_does_not_guess_when_exact_ticker_is_ambiguous(self):
        candidates = [
            SimpleNamespace(ticker="CARM", uid="uid-1", figi="", instrument_type="share"),
            SimpleNamespace(ticker="CARM", uid="uid-2", figi="", instrument_type="share"),
        ]
        class FakeInstruments:
            def find_instrument(self, *, query):
                return SimpleNamespace(instruments=candidates)
        runner = LiveMarketRunner(SimpleNamespace(instruments=FakeInstruments()))
        self.assertEqual(runner._resolve_missing_held_shares([], {"CARM"}), [])

    def test_reports_missing_instrument_without_adding_unrelated_search_results(self):
        class FakeInstruments:
            def find_instrument(self, *, query):
                return SimpleNamespace(instruments=[
                    SimpleNamespace(ticker="OTHER", uid="uid-other", instrument_type="share")
                ])
        runner = LiveMarketRunner(SimpleNamespace(instruments=FakeInstruments()))
        self.assertEqual(runner._resolve_missing_held_shares([], {"SLAV"}), [])

    def test_does_not_call_find_instrument_for_ticker_already_in_catalog(self):
        existing = SimpleNamespace(ticker="AAA", uid="uid-aaa", instrument_type="share")
        class FakeInstruments:
            def find_instrument(self, *, query):
                raise AssertionError("catalog hit must not trigger lookup")
        runner = LiveMarketRunner(SimpleNamespace(instruments=FakeInstruments()))
        self.assertEqual(runner._resolve_missing_held_shares([existing], {"AAA"}), [existing])

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
