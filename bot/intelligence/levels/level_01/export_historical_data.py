"""Export real daily OHLCV candles for the bot's current top-ranked RUB shares.

Read-only: uses LiveMarketRunner's existing T-Invest market-data path and places no orders.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from bot.live_runner import LiveMarketRunner
from bot.tinvest_client import TInvestClient


def number(value) -> float:
    units = getattr(value, "units", None)
    nano = getattr(value, "nano", None)
    if units is None:
        return float(value)
    return float(units) + float(nano or 0) / 1_000_000_000


def _metadata_value(value):
    """Serialize broker metadata without inventing defaults."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "name"):
        return str(value.name)
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def build_coverage_registry(catalog: list[object], candle_history: dict[str, list[object]],
                            as_of: str) -> dict:
    """Build a point-in-time snapshot of current catalog and observed candle coverage.

    This is deliberately not a historical listing/universe reconstruction.
    """
    candle_counts = {
        str(ticker): len(candles)
        for ticker, candles in candle_history.items()
    }
    fields = (
        "uid", "figi", "ticker", "isin", "name", "class_code", "currency",
        "exchange", "sector", "instrument_type", "api_trade_available_flag",
        "buy_available_flag", "sell_available_flag", "ipo_date",
        "first_1day_candle_date", "first_1min_candle_date", "delisted_date",
    )
    instruments = []
    for item in catalog:
        ticker = str(getattr(item, "ticker", "") or "")
        metadata = {
            field: _metadata_value(getattr(item, field, None))
            for field in fields
        }
        metadata["catalog_snapshot_status"] = "present_in_current_TInvest_shares_catalog"
        metadata["daily_candle_export_status"] = (
            "received" if candle_counts.get(ticker, 0) > 0
            else "not_received_or_not_requested"
        )
        metadata["daily_candle_rows"] = candle_counts.get(ticker, 0)
        instruments.append(metadata)

    catalog_tickers = {
        str(getattr(item, "ticker", "") or "")
        for item in catalog
    }
    for ticker, count in sorted(candle_counts.items()):
        if ticker in catalog_tickers:
            continue
        instruments.append({
            "ticker": ticker,
            "catalog_snapshot_status": "not_found_in_current_TInvest_shares_catalog",
            "daily_candle_export_status": "received",
            "daily_candle_rows": count,
        })

    instruments.sort(key=lambda item: (
        str(item.get("ticker") or ""),
        str(item.get("uid") or item.get("figi") or ""),
    ))
    with_candles = sum(item["daily_candle_rows"] > 0 for item in instruments)
    return {
        "data_source": "T-Invest API",
        "snapshot_as_of": as_of,
        "registry_type": "current_catalog_and_observed_candle_coverage",
        "historical_universe_reconstructed": False,
        "catalog_instrument_count": len(instruments),
        "instruments_with_received_daily_candles": with_candles,
        "instruments_without_received_daily_candles": len(instruments) - with_candles,
        "instrument_records": instruments,
        "limitations": [
            "This is a snapshot of the current T-Invest shares catalog, not a point-in-time historical listing universe.",
            "A missing candle count means candles were not received or not requested by this export; it does not prove the instrument had no historical trading.",
            "Historical delistings, suspensions, and past eligibility are not reconstructed.",
        ],
    }


def build_manifest(rows: list[dict], days: int) -> dict:
    """Describe the exported sample and its known selection limitations."""
    by_symbol = {}
    timestamp_keys = set()
    duplicate_symbol_timestamps = 0
    for row in rows:
        symbol = str(row["symbol"])
        timestamp = str(row["timestamp"])
        by_symbol.setdefault(symbol, []).append(timestamp)
        key = (symbol, timestamp)
        if key in timestamp_keys:
            duplicate_symbol_timestamps += 1
        else:
            timestamp_keys.add(key)
    return {
        "data_source": "T-Invest API",
        "row_count": len(rows),
        "unique_symbol_timestamp_count": len(timestamp_keys),
        "duplicate_symbol_timestamp_count": duplicate_symbol_timestamps,
        "data_integrity_status": "duplicates_detected" if duplicate_symbol_timestamps else "unique_symbol_timestamps",
        "candle_interval": "daily",
        "requested_lookback_days": days,
        "sample_start": min(row["timestamp"] for row in rows),
        "sample_end": max(row["timestamp"] for row in rows),
        "symbol_count": len(by_symbol),
        "symbols": {
            symbol: {
                "rows": len(timestamps),
                "start": min(timestamps),
                "end": max(timestamps),
            }
            for symbol, timestamps in sorted(by_symbol.items())
        },
        "selection_method": "current LiveMarketRunner scanner universe",
        "historical_universe_reconstructed": False,
        "data_quality_warnings": (
            ["Duplicate (symbol, timestamp) rows were present in the exported sample."]
            if duplicate_symbol_timestamps else []
        ),
        "limitations": [
            "Current scanner selection is not a point-in-time historical instrument universe.",
            "Survivorship and selection bias may affect historical performance metrics.",
            "Historical listings, delistings, suspensions, and past scanner rankings are not reconstructed.",
            "This dataset must not be presented as an unbiased full-market backtest.",
        ],
    }


def export(path: Path, days: int = 180) -> int:
    if days < 30:
        raise ValueError("days must be at least 30 to support historical evaluation")
    token = os.getenv("INVEST_TOKEN", "").strip()
    if not token:
        raise RuntimeError("INVEST_TOKEN is not configured")

    # The same read-only market scanner used by RNB selects instruments and
    # retrieves real daily candles. No synthetic fallback and no order API.
    client = TInvestClient(token)
    with client._client() as raw_client:
        # Preserve the full current broker shares catalog as a separate,
        # read-only coverage snapshot; the scanner candle set is a shortlist.
        catalog_response = raw_client.instruments.shares()
        current_catalog = list(catalog_response.instruments)
        scan = LiveMarketRunner(raw_client, history_days=days).run()

    rows = []
    for ticker, candles in scan.candle_history.items():
        for candle in candles:
            # Keep the full bar required for realistic historical execution.
            # Missing/invalid OHLC values are skipped rather than synthesized.
            try:
                open_price, high, low, close = (
                    number(getattr(candle, field))
                    for field in ("open", "high", "low", "close")
                )
                volume = float(candle.volume)
            except (AttributeError, TypeError, ValueError, OverflowError):
                continue
            if (
                not all(math.isfinite(value) for value in (open_price, high, low, close, volume))
                or min(open_price, high, low, close) <= 0
                or volume < 0
                or high < max(open_price, low, close)
                or low > min(open_price, high, close)
            ):
                continue
            timestamp = candle.time
            rows.append({
                "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
                "symbol": ticker,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            })

    if not rows:
        raise RuntimeError("T-Invest returned no usable historical candles; CSV was not created")

    rows.sort(key=lambda row: (row["symbol"], row["timestamp"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=("timestamp", "symbol", "open", "high", "low", "close", "volume")
        )
        writer.writeheader()
        writer.writerows(rows)

    symbols = sorted({row["symbol"] for row in rows})
    manifest = build_manifest(rows, days)
    manifest_path = path.with_suffix(path.suffix + ".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"REAL_TINVEST_CSV={path}")
    print(f"DATA_SOURCE=T-Invest API; candle_interval=daily; lookback_days={days}")
    print(f"SYMBOLS={','.join(symbols)}")
    print(f"CANDLE_ROWS={len(rows)}")
    print(f"DATASET_MANIFEST={manifest_path}")
    coverage_path = path.with_suffix(path.suffix + ".coverage.json")
    coverage = build_coverage_registry(
        current_catalog,
        scan.candle_history,
        datetime.now(timezone.utc).isoformat(),
    )
    coverage_path.write_text(
        json.dumps(coverage, indent=2, ensure_ascii=False) + "\\n",
        encoding="utf-8",
    )
    print(f"CURRENT_CATALOG_COVERAGE={coverage_path}")
    print(f"CURRENT_CATALOG_INSTRUMENTS={coverage['catalog_instrument_count']}")
    print(f"CATALOG_INSTRUMENTS_WITH_CANDLES={coverage['instruments_with_received_daily_candles']}")
    print("HISTORICAL_UNIVERSE_RECONSTRUCTED=False")
    print("WARNING=SURVIVORSHIP_AND_SELECTION_BIAS_POSSIBLE")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/level_01_history.csv"))
    parser.add_argument("--days", type=int, default=180)
    args = parser.parse_args()
    export(args.output, args.days)


if __name__ == "__main__":
    main()
