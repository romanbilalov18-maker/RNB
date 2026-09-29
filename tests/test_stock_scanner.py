import unittest
from datetime import datetime, timezone

from bot.models import MarketQuote
from bot.stock_scanner import StockScanner, quote_is_fresh


class Instrument:
    def __init__(
        self,
        uid,
        ticker,
        name,
        currency="RUB",
        instrument_type="share",
        buy_available_flag=True,
        sell_available_flag=True,
        trading_status="normal",
        lot=1,
    ):
        self.uid = uid
        self.ticker = ticker
        self.name = name
        self.currency = currency
        self.instrument_type = instrument_type
        self.buy_available_flag = buy_available_flag
        self.sell_available_flag = sell_available_flag
        self.trading_status = trading_status
        self.lot = lot


class TestStockScanner(unittest.TestCase):
    def setUp(self):
        self.timestamp = datetime.now(timezone.utc)

    def test_selects_rub_shares(self):
        instruments = [
            Instrument("1", "AAA", "AAA"),
            Instrument("2", "BBB", "BBB", currency="USD"),
            Instrument("3", "CCC", "CCC", instrument_type="bond"),
        ]
        quotes = [
            MarketQuote("AAA", 100, self.timestamp, 10_000),
            MarketQuote("BBB", 100, self.timestamp, 100_000),
            MarketQuote("CCC", 100, self.timestamp, 100_000),
        ]

        result = StockScanner().scan(instruments, quotes)

        self.assertEqual([item.ticker for item in result], ["AAA"])

    def test_excludes_untradable_share(self):
        instrument = Instrument(
            "1",
            "AAA",
            "AAA",
            buy_available_flag=False,
        )
        quote = MarketQuote("AAA", 100, self.timestamp, 100_000)

        self.assertEqual(StockScanner().scan([instrument], [quote]), [])

    def test_returns_maximum_requested_candidates(self):
        instruments = [
            Instrument(str(i), f"A{i}", f"A{i}")
            for i in range(20)
        ]
        quotes = [
            MarketQuote(f"A{i}", 100 + i, self.timestamp, 1_000 + i)
            for i in range(20)
        ]

        result = StockScanner(max_candidates=10).scan(instruments, quotes)

        self.assertEqual(len(result), 10)

    def test_candidates_are_ranked_by_score(self):
        instruments = [
            Instrument("1", "LOW", "LOW"),
            Instrument("2", "HIGH", "HIGH"),
        ]
        quotes = [
            MarketQuote("LOW", 100, self.timestamp, 10),
            MarketQuote("HIGH", 100, self.timestamp, 100_000),
        ]

        result = StockScanner().scan(instruments, quotes)

        self.assertEqual(result[0].ticker, "HIGH")

    def test_quote_freshness(self):
        quote = MarketQuote("AAA", 100, self.timestamp, 10)

        self.assertTrue(
            quote_is_fresh(
                quote,
                max_age_seconds=120,
                now=self.timestamp,
            )
        )


if __name__ == "__main__":
    unittest.main()
