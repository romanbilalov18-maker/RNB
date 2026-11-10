"""Out-of-sample historical diagnostics for Level 1 using real OHLCV CSV data.

CSV columns: timestamp,symbol,close,volume. No synthetic market-data fallback.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.stock_analysis import StockAnalyzer
from bot.intelligence.levels.level_01.level_01_engine import aggregate, analyze
from bot.intelligence.levels.level_01.session_gap_diagnostics import (
    find_missing_trading_dates,
    trading_session_date,
)


def load_rows(path: Path):
    grouped = defaultdict(list)
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"timestamp", "symbol", "close", "volume"}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"CSV missing required columns: {', '.join(sorted(missing))}")
        for line, row in enumerate(reader, start=2):
            symbol = (row.get("symbol") or "").strip()
            timestamp = (row.get("timestamp") or "").strip()
            try:
                close = float(row["close"])
                volume = float(row["volume"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"line {line}: close and volume must be numeric") from exc
            if not symbol or not timestamp:
                raise ValueError(f"line {line}: timestamp and symbol are required")
            try:
                parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(f"line {line}: timestamp must be ISO-8601") from exc
            # Date-only/naive timestamps are retained as UTC for compatibility
            # with user-supplied daily CSVs. Offset-aware values are normalized
            # to UTC so lexicographic timezone strings cannot reorder candles.
            if parsed_timestamp.tzinfo is None:
                parsed_timestamp = parsed_timestamp.replace(tzinfo=timezone.utc)
            timestamp_order = parsed_timestamp.astimezone(timezone.utc)
            if not math.isfinite(close) or close <= 0:
                raise ValueError(f"line {line}: close must be finite and > 0")
            if not math.isfinite(volume) or volume < 0:
                raise ValueError(f"line {line}: volume must be finite and >= 0")
            grouped[symbol].append({
                "timestamp": timestamp,
                "_timestamp_order": timestamp_order,
                "close": close,
                "volume": volume,
            })
    for symbol, rows in grouped.items():
        rows.sort(key=lambda row: row["_timestamp_order"])
        if len({row["_timestamp_order"] for row in rows}) != len(rows):
            raise ValueError(f"{symbol}: duplicate timestamps are not allowed")
        for row in rows:
            row.pop("_timestamp_order")
    if not grouped:
        raise ValueError("CSV contains no market rows")
    return grouped



def build_historical_snapshot(symbol: str, candle_window: list[dict]) -> MarketSnapshot:
    """Build an L1 snapshot with the same indicator formulas as the live scanner.

    The window contains completed candles through the signal candle. The
    StockAnalyzer implementation is shared with LiveMarketRunner so historical
    diagnostics cannot silently drift to a different momentum/volatility/
    volume calculation.
    """
    if len(candle_window) < 3:
        raise ValueError("candle_window must contain at least 3 completed candles")
    momentum_period = min(10, len(candle_window) - 1)
    candles = [
        SimpleNamespace(close=row["close"], volume=row["volume"])
        for row in candle_window
    ]
    analysis = StockAnalyzer(
        min_history=len(candle_window),
        momentum_period=momentum_period,
    ).analyze("historical", symbol, candles)
    current = candle_window[-1]
    previous = candle_window[-2]
    return MarketSnapshot(
        symbol=symbol,
        price=current["close"],
        previous_price=previous["close"],
        volume=current["volume"],
        average_volume=analysis.average_volume,
        volatility=analysis.volatility,
        momentum=analysis.momentum,
        # Historical order-book data is not present in daily OHLCV. Keep it
        # unknown; never substitute volume or fabricate a liquidity score.
        liquidity=None,
    )



def _load_dataset_provenance(path: Path) -> dict:
    """Read the exporter sidecar when present; never infer historical universe coverage."""
    manifest_path = path.with_suffix(path.suffix + ".manifest.json")
    if not manifest_path.is_file():
        return {
            "status": "unknown",
            "manifest_file": None,
            "historical_universe_reconstructed": None,
            "warnings": [
                "Dataset provenance manifest is missing; instrument-universe selection cannot be verified.",
                "Do not interpret results as an unbiased full-market backtest.",
            ],
        }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid dataset provenance manifest: {manifest_path}") from exc
    if not isinstance(manifest, dict):
        raise ValueError(f"dataset provenance manifest must contain a JSON object: {manifest_path}")
    return {
        "status": "provided",
        "manifest_file": manifest_path.name,
        "data_source": manifest.get("data_source"),
        "selection_method": manifest.get("selection_method"),
        "historical_universe_reconstructed": manifest.get("historical_universe_reconstructed"),
        "sample_start": manifest.get("sample_start"),
        "sample_end": manifest.get("sample_end"),
        "symbol_count": manifest.get("symbol_count"),
        "limitations": list(manifest.get("limitations") or []),
    }



def load_official_trading_dates(path: Path) -> list[str]:
    """Load a verified exchange-calendar CSV with a required date column."""
    dates = []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if "date" not in (reader.fieldnames or ()):
            raise ValueError("official calendar CSV must contain a 'date' column")
        for line, row in enumerate(reader, start=2):
            value = (row.get("date") or "").strip()
            if not value:
                raise ValueError(f"official calendar line {line}: date is required")
            try:
                dates.append(trading_session_date(value).isoformat())
            except (TypeError, ValueError) as exc:
                raise ValueError(f"official calendar line {line}: invalid date") from exc
    if len(dates) != len(set(dates)):
        raise ValueError("official calendar contains duplicate dates")
    return sorted(dates)


def _metrics(rows):
    if not rows:
        return {"observations": 0, "mean_net_return": None, "score_return_correlation": None,
                "top_quartile_mean_net_return": None, "bottom_quartile_mean_net_return": None,
                "top_minus_bottom_quartile": None, "positive_net_return_rate": None}
    scores = [row["score"] for row in rows]
    returns = [row["net_return"] for row in rows]
    score_mean, return_mean = statistics.mean(scores), statistics.mean(returns)
    score_sd, return_sd = statistics.pstdev(scores), statistics.pstdev(returns)
    covariance = statistics.mean((s - score_mean) * (r - return_mean) for s, r in zip(scores, returns))
    correlation = covariance / (score_sd * return_sd) if score_sd and return_sd else None
    ordered = sorted(rows, key=lambda row: row["score"])
    quartile_size = max(1, len(ordered) // 4)
    low = [row["net_return"] for row in ordered[:quartile_size]]
    high = [row["net_return"] for row in ordered[-quartile_size:]]
    high_mean, low_mean = statistics.mean(high), statistics.mean(low)
    return {
        "observations": len(rows),
        "mean_net_return": return_mean,
        "score_return_correlation": correlation,
        "top_quartile_mean_net_return": high_mean,
        "bottom_quartile_mean_net_return": low_mean,
        "top_minus_bottom_quartile": high_mean - low_mean,
        "positive_net_return_rate": sum(value > 0 for value in returns) / len(returns),
    }



def _cost_sensitivity(rows, one_way_costs_bps=(0, 5, 10, 25, 50, 100)):
    """Show how assumed round-trip costs change the same gross outcomes.

    These are transparent scenarios, not broker tariff estimates. The caller's
    selected cost_bps remains the value used by the primary metrics.
    """
    scenarios = []
    for one_way_bps in one_way_costs_bps:
        cost_fraction = 2.0 * one_way_bps / 10000.0
        net_returns = [row["gross_return"] - cost_fraction for row in rows]
        scenarios.append({
            "assumed_one_way_cost_bps": one_way_bps,
            "assumed_round_trip_cost_bps": 2 * one_way_bps,
            "observations": len(net_returns),
            "mean_net_return": statistics.mean(net_returns) if net_returns else None,
            "positive_net_return_rate": (
                sum(value > 0 for value in net_returns) / len(net_returns)
                if net_returns else None
            ),
        })
    return scenarios


def evaluate(path: Path, window: int = 20, horizon: int = 5,
             data_source: str = "user_supplied_csv", cost_bps: float = 0.0,
             max_gap_days: int = 7, official_calendar_path: Path | None = None):
    if window < 3 or horizon < 1:
        raise ValueError("window must be >= 3 and horizon must be >= 1")
    if not math.isfinite(cost_bps) or cost_bps < 0:
        raise ValueError("cost_bps must be finite and >= 0")
    if not isinstance(max_gap_days, int) or isinstance(max_gap_days, bool) or max_gap_days < 1:
        raise ValueError("max_gap_days must be a positive integer")
    grouped = load_rows(path)
    predictions = []
    skipped_gap_outcomes = 0
    analyzer_totals = defaultdict(lambda: {"count": 0, "score_sum": 0.0, "unavailable": 0})
    for symbol, rows in grouped.items():
        if len(rows) <= window + horizon:
            continue
        # Non-overlapping forward outcomes prevent the same future price move from
        # being counted repeatedly. Every symbol is evaluated on its own timeline.
        for index in range(window - 1, len(rows) - horizon, horizon):
            # The signal candle is the final candle in the lookback window.
            # The outcome starts at that close and ends horizon rows later.
            span = rows[index - window + 1:index + horizon + 1]
            timestamps = [
                datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                for row in span
            ]
            timestamps = [
                stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
                for stamp in timestamps
            ]
            if any(
                (later.astimezone(timezone.utc) - earlier.astimezone(timezone.utc)).total_seconds()
                > max_gap_days * 86400
                for earlier, later in zip(timestamps, timestamps[1:])
            ):
                skipped_gap_outcomes += 1
                continue
            candle_window = rows[index - window + 1:index + 1]
            current = rows[index]
            snapshot = build_historical_snapshot(symbol, candle_window)
            results = analyze(snapshot)
            score = aggregate(results)
            gross_return = rows[index + horizon]["close"] / current["close"] - 1.0
            # Explicit assumed round-trip cost, not a claim about actual broker costs.
            net_return = gross_return - 2.0 * cost_bps / 10000.0
            predictions.append({
                "symbol": symbol, "timestamp": current["timestamp"], "score": score,
                "gross_return": gross_return, "net_return": net_return,
            })
            for result in results:
                if result.analyzer == "data_quality":
                    continue
                record = analyzer_totals[result.analyzer]
                record["count"] += 1
                record["score_sum"] += result.score
                if result.confidence <= 0:
                    record["unavailable"] += 1

    if not predictions:
        raise ValueError(f"Not enough rows. Each symbol needs more than window+horizon rows (window={window}, horizon={horizon}).")

    # Chronological holdout: latest 30% of observations per symbol. The earlier
    # observations are reported separately and are never used to tune parameters.
    by_symbol = defaultdict(list)
    for row in predictions:
        by_symbol[row["symbol"]].append(row)
    development, holdout = [], []
    for symbol_rows in by_symbol.values():
        split = max(1, int(len(symbol_rows) * 0.7))
        if len(symbol_rows) - split < 1:
            development.extend(symbol_rows)
        else:
            development.extend(symbol_rows[:split])
            holdout.extend(symbol_rows[split:])

    dataset_provenance = _load_dataset_provenance(path)
    calendar_diagnostics = None
    if official_calendar_path is not None:
        official_dates = load_official_trading_dates(official_calendar_path)
        calendar_diagnostics = {
            "calendar_file": official_calendar_path.name,
            "calendar_dates": len(official_dates),
            "missing_dates_by_symbol": {
                symbol: find_missing_trading_dates(
                    official_dates, [row["timestamp"] for row in rows]
                )
                for symbol, rows in sorted(grouped.items())
            },
        }
    report = {
        "status": "completed",
        "data_source": data_source,
        "input_file": path.name,
        "dataset_provenance": dataset_provenance,
        "bias_assessment": (
            "known_current_universe_selection_bias"
            if dataset_provenance.get("historical_universe_reconstructed") is False
            else "unknown"
            if dataset_provenance.get("status") == "unknown"
            else "not_assessed"
        ),
        "symbols": sorted(grouped),
        "input_rows": sum(len(rows) for rows in grouped.values()),
        "evaluated_observations": len(predictions),
        "skipped_outcomes_due_to_data_gaps": skipped_gap_outcomes,
        "official_calendar_gap_diagnostics": calendar_diagnostics,
        "maximum_allowed_observation_gap_days": max_gap_days,
        "lookback_window": window,
        "indicator_source": "bot.stock_analysis.StockAnalyzer (shared with LiveMarketRunner)",
        "momentum_period_rows": min(10, window - 1),
        "forward_horizon_rows": horizon,
        "non_overlapping_outcomes": True,
        "assumed_round_trip_cost_bps": cost_bps,
        "cost_sensitivity": _cost_sensitivity(predictions),
        "metrics": {
            "all": _metrics(predictions),
            "development_chronological": _metrics(development),
            "holdout_chronological": _metrics(holdout),
        },
        "analyzers": {
            name: {
                "observations": values["count"],
                "mean_score": values["score_sum"] / values["count"] if values["count"] else None,
                "unavailable_rate": values["unavailable"] / values["count"] if values["count"] else None,
            } for name, values in sorted(analyzer_totals.items())
        },
        "limitations": [
            *dataset_provenance.get("limitations", []),
            *dataset_provenance.get("warnings", []),
            "Diagnostic only; it does not establish profitability or statistical significance.",
            "Holdout is chronological but small datasets may not provide a meaningful holdout.",
            "Cost is an explicit assumed round-trip basis-point deduction; actual spread, fees and slippage may differ.",
            "Corporate actions, market sessions, survivorship bias and instrument-specific trading constraints are not modeled.",
            "Liquidity remains unavailable unless supplied by a verified source.",
            "Outcomes crossing gaps longer than maximum_allowed_observation_gap_days are skipped; this calendar-day threshold is a conservative diagnostic, not an exchange calendar.",
            "Indicator definitions must be matched to the live data producer before interpreting results.",
        ],
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path, help="Real OHLCV CSV; no synthetic fallback")
    parser.add_argument("--window", type=int, default=20)
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--data-source", default="user_supplied_csv")
    parser.add_argument("--cost-bps", type=float, default=0.0,
                        help="Assumed one-way cost in basis points; deducted twice per round trip")
    parser.add_argument("--official-calendar-csv", type=Path, help="Verified official trading calendar CSV with a date column; never generated from weekdays")
    parser.add_argument("--output", type=Path, default=Path("level_01_historical_report.json"))
    args = parser.parse_args()
    report = evaluate(args.csv, args.window, args.horizon, args.data_source, args.cost_bps, official_calendar_path=args.official_calendar_csv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"LEVEL_01_HISTORICAL_REPORT={args.output}")


if __name__ == "__main__":
    main()
