import csv
import json
from pathlib import Path
import tempfile
import unittest

from bot.historical_portfolio_backtest import load_dataset


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
        self.assertEqual(metadata["AAA"]["lot"], 10)
        self.assertEqual(manifest["data_source"], "T-Invest API")

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


if __name__ == "__main__":
    unittest.main()
