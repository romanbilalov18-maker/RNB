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

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.level_01_engine import aggregate, analyze


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


def evaluate(path: Path, window: int = 20, horizon: int = 5,
             data_source: str = "user_supplied_csv", cost_bps: float = 0.0):
    if window < 3 or horizon < 1:
        raise ValueError("window must be >= 3 and horizon must be >= 1")
    if not math.isfinite(cost_bps) or cost_bps < 0:
        raise ValueError("cost_bps must be finite and >= 0")
    grouped = load_rows(path)
    predictions = []
    analyzer_totals = defaultdict(lambda: {"count": 0, "score_sum": 0.0, "unavailable": 0})
    for symbol, rows in grouped.items():
        if len(rows) <= window + horizon:
            continue
        # Non-overlapping forward outcomes prevent the same future price move from
        # being counted repeatedly. Every symbol is evaluated on its own timeline.
        for index in range(window, len(rows) - horizon, horizon):
            history = rows[index - window:index]
            current, previous = rows[index], rows[index - 1]
            avg_volume = statistics.mean(row["volume"] for row in history)
            returns = [history[i]["close"] / history[i - 1]["close"] - 1.0
                       for i in range(1, len(history))]
            volatility = statistics.pstdev(returns) if len(returns) > 1 else 0.0
            momentum = current["close"] / history[0]["close"] - 1.0
            snapshot = MarketSnapshot(
                symbol=symbol, price=current["close"], previous_price=previous["close"],
                volume=current["volume"], average_volume=avg_volume if avg_volume > 0 else None,
                volatility=volatility, momentum=momentum, liquidity=None,
            )
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
        "lookback_window": window,
        "forward_horizon_rows": horizon,
        "non_overlapping_outcomes": True,
        "assumed_round_trip_cost_bps": cost_bps,
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
    parser.add_argument("--output", type=Path, default=Path("level_01_historical_report.json"))
    args = parser.parse_args()
    report = evaluate(args.csv, args.window, args.horizon, args.data_source, args.cost_bps)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"LEVEL_01_HISTORICAL_REPORT={args.output}")


if __name__ == "__main__":
    main()
