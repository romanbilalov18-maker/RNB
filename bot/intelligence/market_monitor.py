from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from bot.intelligence.tinvest_runner import run_real_market_intelligence


def _finite_or_none(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _level_metrics(result) -> dict[str, float | None]:
    metrics: dict[str, float | None] = {}
    for number in range(1, 16):
        level = getattr(result, f"level_{number:02d}", None)
        metrics[f"level_{number:02d}_score"] = (
            _finite_or_none(getattr(level, "score", None)) if level is not None else None
        )
        metrics[f"level_{number:02d}_confidence"] = (
            _finite_or_none(getattr(level, "confidence", None))
            if level is not None
            else None
        )
    return metrics


def _monitor_parts(item):
    """Normalize the monitor's read-only runner result; extra diagnostics are ignored."""
    if not isinstance(item, (tuple, list)) or len(item) < 3:
        raise ValueError("monitor runner results must contain analysis, intelligence, and price")
    analysis, result, current_price = item[:3]
    metadata = item[8] if len(item) > 8 and isinstance(item[8], dict) else {}
    return analysis, result, current_price, metadata


def _record(analysis, result, current_price: float, timestamp: str) -> dict:
    price = _finite_or_none(current_price)
    if price is None or price <= 0:
        raise ValueError(f"monitor price must be finite and positive for {analysis.ticker}")
    level_01 = result.level_01
    change = None
    analyzer_results = getattr(level_01, "analyzer_results", ())
    if analyzer_results:
        change = analyzer_results[0].metrics.get("change")

    record = {
        "timestamp": timestamp,
        "symbol": analysis.ticker,
        "price": price,
        # Backward-compatible field name; this is the change from the
        # snapshot's previous_price, not necessarily the exchange's daily change.
        "daily_change": _finite_or_none(change),
        "price_change_from_previous": _finite_or_none(change),
        "intelligence": _finite_or_none(result.overall_score),
        "confidence": _finite_or_none(result.overall_confidence),
        "consistency": _finite_or_none(result.overall_consistency),
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
    universe_output_path: str | None = None,
    sleep_fn=time.sleep,
    run_fn=run_real_market_intelligence,
    clock_fn=time.monotonic,
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
    universe_path = Path(universe_output_path) if universe_output_path else path.with_name(path.stem + ".universe.jsonl")
    universe_path.parent.mkdir(parents=True, exist_ok=True)

    cycles = max(1, (duration_minutes + interval_minutes - 1) // interval_minutes)
    total_records = 0

    for cycle in range(cycles):
        cycle_started = clock_fn()
        timestamp = datetime.now(timezone.utc).isoformat()
        results = run_fn(token, limit=limit)
        if not results:
            raise RuntimeError("No instruments were successfully analyzed")

        normalized_results = [_monitor_parts(item) for item in results]
        scan_metadata = next((metadata for _, _, _, metadata in normalized_results if metadata), {})
        universe_record = {
            "timestamp": timestamp,
            "symbols": sorted({str(analysis.ticker) for analysis, _, _, _ in normalized_results}),
            "instrument_count": len({str(analysis.ticker) for analysis, _, _, _ in normalized_results}),
            "scanner_shortlist_count": scan_metadata.get("scanner_shortlist_count"),
            "buy_candidate_count": scan_metadata.get("buy_candidate_count"),
            "fresh_quote_count": scan_metadata.get("fresh_quote_count"),
            "active_session_count": scan_metadata.get("active_session_count"),
            "monitor_analyzed_count": scan_metadata.get("monitor_analyzed_count", len(normalized_results)),
            "monitor_limit": scan_metadata.get("monitor_limit", limit),
            "scope": scan_metadata.get("scope", "instruments returned by current read-only monitor scan; not the full historical market universe"),
        }
        with universe_path.open("a", encoding="utf-8") as universe_handle:
            universe_handle.write(json.dumps(universe_record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")

        with path.open("a", encoding="utf-8") as handle:
            for analysis, result, current_price, _ in normalized_results:
                handle.write(
                    json.dumps(
                        _record(analysis, result, current_price, timestamp),
                        ensure_ascii=False,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                )
                total_records += 1

        print(
            f"Monitor cycle {cycle + 1}/{cycles}: "
            f"instruments={len(results)} timestamp={timestamp}"
        )

        if cycle + 1 < cycles:
            # Keep scan start times approximately interval_minutes apart,
            # accounting for time spent fetching and analyzing market data.
            elapsed = max(0.0, clock_fn() - cycle_started)
            sleep_fn(max(0.0, interval_minutes * 60 - elapsed))

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
    print("Decision Engine: NOT RUN BY THIS READ-ONLY MONITOR; the main virtual-trading cycle evaluates it separately.")


if __name__ == "__main__":
    main()
