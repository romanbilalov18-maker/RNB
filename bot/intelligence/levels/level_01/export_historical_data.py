"""Export real daily OHLCV candles for the bot's current top-ranked RUB shares.

Read-only: uses LiveMarketRunner's existing T-Invest market-data path and places no orders.
"""
from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.live_runner import LiveMarketRunner
from bot.tinvest_client import TInvestClient


def number(value) -> float:
    units = getattr(value, "units", None)
    nano = getattr(value, "nano", None)
    if units is None:
        return float(value)
    return float(units) + float(nano or 0) / 1_000_000_000


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
            close = number(candle.close)
            volume = float(candle.volume)
            timestamp = candle.time
            if close <= 0:
                continue
            rows.append({
                "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
                "symbol": ticker,
                "close": close,
                "volume": volume,
            })

    if not rows:
        raise RuntimeError("T-Invest returned no usable historical candles; CSV was not created")

    rows.sort(key=lambda row: (row["symbol"], row["timestamp"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("timestamp", "symbol", "close", "volume"))
        writer.writeheader()
        writer.writerows(rows)

    symbols = sorted({row["symbol"] for row in rows})
    print(f"REAL_TINVEST_CSV={path}")
    print(f"DATA_SOURCE=T-Invest API; candle_interval=daily; lookback_days={days}")
    print(f"SYMBOLS={','.join(symbols)}")
    print(f"CANDLE_ROWS={len(rows)}")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/level_01_history.csv"))
    parser.add_argument("--days", type=int, default=180)
    args = parser.parse_args()
    export(args.output, args.days)


if __name__ == "__main__":
    main()
