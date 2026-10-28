import unittest
from types import SimpleNamespace

from bot.position_health import assess_position_health


def candles(closes):
    return [SimpleNamespace(close=value, is_complete=True) for value in closes]


class PositionHealthTests(unittest.TestCase):
    def test_missing_fresh_price_triggers_market_data_verification_not_sell(self):
        result = assess_position_health(
            "TEST", candles([10, 10, 10, 10, 10, 10]),
            current_price_available=False,
        )
        self.assertEqual(result.status, "QUOTE_UNAVAILABLE")
        self.assertIn("do not infer a sell", result.recommendation.lower())

    def test_flat_prices_for_five_sessions_trigger_stagnation_review(self):
        result = assess_position_health(
            "TEST", candles([10, 10.001, 10, 10, 10.001, 10]),
            current_price_available=True,
        )
        self.assertEqual(result.status, "PROLONGED_STAGNATION")
        self.assertEqual(result.flat_sessions, 6)
        self.assertIn("REVIEW", result.recommendation)

    def test_stagnation_plus_bearish_momentum_escalates_exit_review(self):
        result = assess_position_health(
            "TEST", candles([10, 10, 10, 10, 10, 10]),
            current_price_available=True,
            momentum=-0.03,
            trend_strength=-0.2,
        )
        self.assertEqual(result.recommendation, "EXIT_REVIEW_WITH_EXISTING_RISK_RULES")

    def test_stagnation_alone_does_not_recommend_sell(self):
        result = assess_position_health(
            "TEST", candles([10, 10, 10, 10, 10, 10]),
            current_price_available=True,
            momentum=0.01,
            trend_strength=0.2,
        )
        self.assertEqual(
            result.recommendation,
            "HOLD_AND_REVIEW_LIQUIDITY_TREND_AND_INSTRUMENT_STATUS",
        )

    def test_incomplete_candles_are_ignored(self):
        data = candles([10, 10, 10, 10, 10])
        data[-1].is_complete = False
        result = assess_position_health(
            "TEST", data, current_price_available=True,
        )
        self.assertEqual(result.candles_checked, 4)
        self.assertEqual(result.status, "NORMAL_MONITORING")

    def test_low_range_over_ten_sessions_triggers_review(self):
        result = assess_position_health(
            "TEST", candles([10, 10.01, 10.02, 10.01, 10.00, 10.01, 10.02, 10.01, 10, 10.01]),
            current_price_available=True,
        )
        self.assertEqual(result.status, "PROLONGED_STAGNATION")
        self.assertIsNotNone(result.recent_range_pct)

    def test_invalid_candle_prices_are_ignored(self):
        result = assess_position_health(
            "TEST", candles([10, 0, float("nan"), 10, 10, 10]),
            current_price_available=True,
        )
        self.assertEqual(result.candles_checked, 4)


if __name__ == "__main__":
    unittest.main()
