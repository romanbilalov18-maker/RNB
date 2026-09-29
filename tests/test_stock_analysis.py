import unittest
from dataclasses import dataclass

from bot.stock_analysis import StockAnalyzer


@dataclass
class Candle:
    close: float
    volume: int


def make_candles(prices, volumes=None):
    volumes = volumes or [1000] * len(prices)
    return [
        Candle(close=price, volume=volume)
        for price, volume in zip(prices, volumes)
    ]


class Candidate:
    def __init__(self, instrument_id, ticker):
        self.instrument_id = instrument_id
        self.ticker = ticker


class TestStockAnalyzer(unittest.TestCase):
    def test_rejects_insufficient_history(self):
        analyzer = StockAnalyzer(min_history=20)

        with self.assertRaises(ValueError):
            analyzer.analyze("1", "AAA", make_candles([100] * 10))

    def test_calculates_positive_momentum(self):
        prices = list(range(100, 125))
        result = StockAnalyzer(min_history=20).analyze(
            "1",
            "AAA",
            make_candles(prices),
        )

        self.assertGreater(result.momentum, 0)
        self.assertGreater(result.return_period, 0)
        self.assertGreater(result.trend_strength, 0)

    def test_volume_ratio_increases_with_recent_volume(self):
        volumes = [1000] * 20 + [5000] * 5
        prices = [100 + index for index in range(25)]

        result = StockAnalyzer(min_history=20).analyze(
            "1",
            "AAA",
            make_candles(prices, volumes),
        )

        self.assertGreater(result.volume_ratio, 1.0)

    def test_rank_orders_candidates_by_score(self):
        analyzer = StockAnalyzer(min_history=20)

        candidates = [
            Candidate("1", "WEAK"),
            Candidate("2", "STRONG"),
        ]
        history = {
            "1": make_candles([100] * 25),
            "2": make_candles(list(range(100, 125))),
        }

        result = analyzer.rank(candidates, history)

        self.assertEqual(result[0].ticker, "STRONG")


if __name__ == "__main__":
    unittest.main()
