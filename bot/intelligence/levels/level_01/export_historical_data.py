"""Export real daily OHLCV candles for the bot's current top-ranked RUB shares.

Read-only: uses LiveMarketRunner's existing T-Invest market-data path and places no orders.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path

from bot.live_runner import LiveMarketRunner
from bot.tinvest_client import TInvestClient


def number(value) -> float:
    units = getattr(value, "units", None)
    nano = getattr(value, "nano", None)
    if units is None:
        return float(value)
    return float(units) + float(nano or 0) / 1_000_000_000


def build_manifest(rows: list[dict], days: int) -> dict:
    """Describe the exported sample and its known selection limitations."""
    by_symbol = {}
    for row in rows:
        by_symbol.setdefault(row["symbol"], []).append(row["timestamp"])
    return {
        "data_source": "T-Invest API",
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
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\\n",
        encoding="utf-8",
    )
    print(f"REAL_TINVEST_CSV={path}")
    print(f"DATA_SOURCE=T-Invest API; candle_interval=daily; lookback_days={days}")
    print(f"SYMBOLS={','.join(symbols)}")
    print(f"CANDLE_ROWS={len(rows)}")
    print(f"DATASET_MANIFEST={manifest_path}")
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
