import csv
import json
from pathlib import Path
import tempfile
import unittest

from bot.historical_portfolio_backtest import _build_open_position_report, load_dataset
from bot.virtual_portfolio import VirtualPortfolio


class HistoricalPortfolioDatasetTests(unittest.TestCase):
    def _write_dataset(self, root: Path, *, data_source="T-Invest API", duplicate=False):
        csv_path = root / "history.csv"
        rows = [
            ["2025-01-02T10:00:00+03:00", "AAA", "100", "105", "99", "103", "1000"],
        ]
        if duplicate:
            rows.append(rows[0])
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["timestamp", "symbol", "open", "high", "low", "close", "volume"])
            writer.writerows(rows)
        coverage = {
            "data_source": data_source,
            "instrument_records": [{
                "ticker": "AAA",
                "uid": "uid-aaa",
                "figi": "figi-aaa",
                "lot": 10,
                "exchange": "MOEX",
                "catalog_snapshot_status": "present_in_current_TInvest_shares_catalog",
            }],
        }
        manifest = {
            "data_source": data_source,
            "data_integrity_status": "duplicates_detected" if duplicate else "unique_symbol_timestamps",
            "candle_completion_status": "verified_completed_only",
            "sample_start": rows[0][0],
            "sample_end": rows[-1][0],
            "selection_method": "current LiveMarketRunner scanner universe",
        }
        csv_path.with_suffix(".csv.coverage.json").write_text(
            json.dumps(coverage), encoding="utf-8"
        )
        csv_path.with_suffix(".csv.manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return csv_path

    def test_loads_real_tinvest_ohlcv_and_broker_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self._write_dataset(Path(temp))
            candles, metadata, manifest = load_dataset(path)
        self.assertEqual(len(candles["AAA"]), 1)
        self.assertEqual(candles["AAA"][0].open, 100.0)
        self.assertEqual(candles["AAA"][0].close, 103.0)
        self.assertIs(candles["AAA"][0].is_complete, True)
        self.assertEqual(metadata["AAA"]["lot"], 10)
        self.assertEqual(manifest["data_source"], "T-Invest API")


    def test_rejects_dataset_without_verified_completed_candle_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self._write_dataset(Path(temp))
            manifest_path = path.with_suffix(".csv.manifest.json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.pop("candle_completion_status")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "verified completed daily candles"):
                load_dataset(path)

    def test_rejects_non_tinvest_data_source(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self._write_dataset(Path(temp), data_source="synthetic")
            with self.assertRaisesRegex(ValueError, "only datasets marked as T-Invest API"):
                load_dataset(path)

    def test_rejects_duplicate_ticker_timestamp_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self._write_dataset(Path(temp), duplicate=True)
            with self.assertRaisesRegex(ValueError, "duplicate symbol/timestamp"):
                load_dataset(path)

    def test_rejects_missing_historical_instrument_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self._write_dataset(Path(temp))
            coverage_path = path.with_suffix(".csv.coverage.json")
            coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
            coverage["instrument_records"] = []
            coverage_path.write_text(json.dumps(coverage), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no matching current T-Invest catalog metadata"):
                load_dataset(path)

    def test_load_dataset_can_filter_to_fixed_ticker_universe(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self._write_dataset(Path(temp))
            candles, metadata, _ = load_dataset(path, tickers={" aaa "})
        self.assertEqual(set(candles), {"AAA"})
        self.assertIn("AAA", metadata)

    def test_fixed_ticker_universe_fails_if_symbol_is_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self._write_dataset(Path(temp))
            with self.assertRaisesRegex(ValueError, "absent from T-Invest dataset: BBB"):
                load_dataset(path, tickers={"AAA", "BBB"})

    def test_fixed_ticker_universe_rejects_empty_filter(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self._write_dataset(Path(temp))
            with self.assertRaisesRegex(ValueError, "at least one non-empty symbol"):
                load_dataset(path, tickers=set())

    def test_open_position_report_marks_missing_final_quotes_as_unknown(self):
        portfolio = VirtualPortfolio(10_000, commission_rate=0.001)
        portfolio.buy("AAA", 2, 100, "2025-01-02T10:00:00+00:00")
        portfolio.buy("BBB", 3, 50, "2025-01-02T10:00:00+00:00")

        details, summary = _build_open_position_report(
            portfolio,
            {"AAA": 110.0},
            [],
        )

        by_ticker = {item["ticker"]: item for item in details}
        self.assertEqual(by_ticker["AAA"]["valuation_status"], "PRICED")
        self.assertEqual(by_ticker["AAA"]["market_value"], 220.0)
        self.assertEqual(by_ticker["BBB"]["valuation_status"], "MISSING_FINAL_QUOTE")
        self.assertIsNone(by_ticker["BBB"]["market_price"])
        self.assertIsNone(by_ticker["BBB"]["market_value"])
        self.assertIsNone(by_ticker["BBB"]["estimated_net_if_sold_now"])
        self.assertFalse(summary["valuation_complete"])
        self.assertEqual(summary["priced_positions"], 1)
        self.assertEqual(summary["unpriced_positions"], 1)
        self.assertEqual(summary["missing_final_quote_tickers"], ["BBB"])

    def test_open_position_report_summarizes_historical_missing_quote_cycles(self):
        from types import SimpleNamespace

        portfolio = VirtualPortfolio(10_000)
        portfolio.buy("AAA", 1, 100, "2025-01-02T10:00:00+00:00")
        curve = [
            SimpleNamespace(unpriced_tickers=("AAA", "BBB")),
            SimpleNamespace(unpriced_tickers=()),
            SimpleNamespace(unpriced_tickers=("BBB",)),
        ]

        _, summary = _build_open_position_report(portfolio, {"AAA": 101.0}, curve)

        self.assertEqual(summary["incomplete_mark_to_market_cycles"], 2)
        self.assertEqual(
            summary["unpriced_ticker_cycle_counts"],
            {"AAA": 1, "BBB": 2},
        )


if __name__ == "__main__":
    unittest.main()
