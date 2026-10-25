from __future__ import annotations

import unittest
from types import SimpleNamespace

from bot.main import _format_selected_analysis_line


class SelectedMarketDataReportingTests(unittest.TestCase):
    def setUp(self):
        # Isolated unit-test input only; this fixture is never used by the bot
        # as market data and cannot reach the broker or execution layer.
        self.analysis = SimpleNamespace(ticker="SBER", score=0.81234)

    def test_formats_available_quote_and_lot(self):
        line = _format_selected_analysis_line(
            self.analysis, {"SBER": 250.5}, {"SBER": 10}
        )
        self.assertEqual(line, "- SBER: price=250.50, lot=10, score=0.8123")

    def test_missing_quote_is_reported_without_substitution(self):
        line = _format_selected_analysis_line(self.analysis, {}, {"SBER": 10})
        self.assertIn("price=unavailable (no verified fresh quote)", line)
        self.assertIn("lot=10", line)

    def test_missing_lot_size_is_reported_without_exception(self):
        line = _format_selected_analysis_line(
            self.analysis, {"SBER": 250.5}, {}
        )
        self.assertIn("price=250.50", line)
        self.assertIn("lot=unavailable (missing/invalid lot size)", line)

    def test_non_finite_and_non_positive_quotes_are_not_displayed_as_prices(self):
        for price in (float("nan"), float("inf"), float("-inf"), 0, -1):
            with self.subTest(price=price):
                line = _format_selected_analysis_line(
                    self.analysis, {"SBER": price}, {"SBER": 10}
                )
                self.assertIn(
                    "price=unavailable (no verified fresh quote)", line
                )


if __name__ == "__main__":
    unittest.main()
