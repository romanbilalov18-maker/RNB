from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from bot.intelligence.tinvest_runner import run_real_market_intelligence


def _level_metrics(result) -> dict[str, float | None]:
    metrics: dict[str, float | None] = {}
    for number in range(1, 16):
        level = getattr(result, f"level_{number:02d}", None)
        metrics[f"level_{number:02d}_score"] = (
            float(getattr(level, "score")) if level is not None and getattr(level, "score", None) is not None else None
        )
        metrics[f"level_{number:02d}_confidence"] = (
            float(getattr(level, "confidence"))
            if level is not None and getattr(level, "confidence", None) is not None
            else None
        )
    return metrics


def _record(analysis, result, current_price: float, timestamp: str) -> dict:
    level_01 = result.level_01
    change = None
    analyzer_results = getattr(level_01, "analyzer_results", ())
    if analyzer_results:
        change = analyzer_results[0].metrics.get("change")

    record = {
        "timestamp": timestamp,
        "symbol": analysis.ticker,
        "price": float(current_price),
        "daily_change": float(change) if change is not None else None,
        "intelligence": float(result.overall_score),
        "confidence": float(result.overall_confidence),
        "consistency": float(result.overall_consistency),
        "warnings": list(result.warnings),
    }
    record.update(_level_metrics(result))
    return record


def run_monitor(
    token: str,
    duration_minutes: int = 60,
    interval_minutes: int = 5,
    limit: int = 10,
    output_path: str = "data/intelligence_monitor.jsonl",
    sleep_fn=time.sleep,
    run_fn=run_real_market_intelligence,
) -> int:
    if not token.strip():
        raise ValueError("T-Invest token is required")
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be positive")
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")
    if limit <= 0:
        raise ValueError("limit must be positive")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    cycles = max(1, (duration_minutes + interval_minutes - 1) // interval_minutes)
    total_records = 0

    for cycle in range(cycles):
        timestamp = datetime.now(timezone.utc).isoformat()
        results = run_fn(token, limit=limit)
        if not results:
            raise RuntimeError("No instruments were successfully analyzed")

        with path.open("a", encoding="utf-8") as handle:
            for analysis, result, current_price in results:
                handle.write(
                    json.dumps(
                        _record(analysis, result, current_price, timestamp),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )
                total_records += 1

        print(
            f"Monitor cycle {cycle + 1}/{cycles}: "
            f"instruments={len(results)} timestamp={timestamp}"
        )

        if cycle + 1 < cycles:
            sleep_fn(interval_minutes * 60)

    return total_records


def main() -> None:
    token = os.getenv("INVEST_TOKEN", "").strip()
    duration = int(os.getenv("MONITOR_DURATION_MINUTES", "60"))
    interval = int(os.getenv("MONITOR_INTERVAL_MINUTES", "5"))
    limit = int(os.getenv("MONITOR_LIMIT", "10"))
    output = os.getenv("MONITOR_OUTPUT", "data/intelligence_monitor.jsonl")

    records = run_monitor(
        token,
        duration_minutes=duration,
        interval_minutes=interval,
        limit=limit,
        output_path=output,
    )
    print(f"Monitor finished: {records} records")
    print("Trade execution: DISABLED")
    print("Decision Engine: NOT CONNECTED")


if __name__ == "__main__":
    main()
