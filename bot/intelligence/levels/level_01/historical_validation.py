"""Historical validation harness for Level 1 using a user-supplied real OHLCV CSV.

CSV columns: timestamp,symbol,close,volume
Rows must be chronological per symbol. This tool never downloads or fabricates market data.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
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
            if not math.isfinite(close) or close <= 0:
                raise ValueError(f"line {line}: close must be finite and > 0")
            if not math.isfinite(volume) or volume < 0:
                raise ValueError(f"line {line}: volume must be finite and >= 0")
            grouped[symbol].append({"timestamp": timestamp, "close": close, "volume": volume})
    for symbol, rows in grouped.items():
        rows.sort(key=lambda row: row["timestamp"])
        if len({row["timestamp"] for row in rows}) != len(rows):
            raise ValueError(f"{symbol}: duplicate timestamps are not allowed")
    if not grouped:
        raise ValueError("CSV contains no market rows")
    return grouped


def evaluate(path: Path, window: int = 20, horizon: int = 5):
    if window < 3 or horizon < 1:
        raise ValueError("window must be >= 3 and horizon must be >= 1")
    grouped = load_rows(path)
    predictions = []
    analyzer_totals = defaultdict(lambda: {"count": 0, "score_sum": 0.0, "unavailable": 0})
    for symbol, rows in grouped.items():
        if len(rows) <= window + horizon:
            continue
        for index in range(window, len(rows) - horizon):
            history = rows[index - window:index]
            current = rows[index]
            previous = rows[index - 1]
            prior_volumes = [row["volume"] for row in history]
            avg_volume = statistics.mean(prior_volumes)
            returns = [
                history[i]["close"] / history[i - 1]["close"] - 1.0
                for i in range(1, len(history))
            ]
            volatility = statistics.pstdev(returns) if len(returns) > 1 else 0.0
            momentum = current["close"] / rows[index - min(window, index)]["close"] - 1.0
            snapshot = MarketSnapshot(
                symbol=symbol,
                price=current["close"],
                previous_price=previous["close"],
                volume=current["volume"],
                average_volume=avg_volume if avg_volume > 0 else None,
                volatility=volatility,
                momentum=momentum,
                liquidity=None,
            )
            results = analyze(snapshot)
            score = aggregate(results)
            future_return = rows[index + horizon]["close"] / current["close"] - 1.0
            predictions.append({
                "symbol": symbol,
                "timestamp": current["timestamp"],
                "score": score,
                "future_return": future_return,
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
        raise ValueError(
            f"Not enough rows. Each symbol needs more than window+horizon rows "
            f"(currently window={window}, horizon={horizon})."
        )

    scores = [row["score"] for row in predictions]
    outcomes = [row["future_return"] for row in predictions]
    mean_outcome = statistics.mean(outcomes)
    score_mean = statistics.mean(scores)
    covariance = statistics.mean((s - score_mean) * (r - mean_outcome) for s, r in zip(scores, outcomes))
    score_sd = statistics.pstdev(scores)
    outcome_sd = statistics.pstdev(outcomes)
    correlation = covariance / (score_sd * outcome_sd) if score_sd and outcome_sd else None
    high_cut = statistics.quantiles(scores, n=4)[2] if len(scores) >= 4 else max(scores)
    low_cut = statistics.quantiles(scores, n=4)[0] if len(scores) >= 4 else min(scores)
    high = [row["future_return"] for row in predictions if row["score"] >= high_cut]
    low = [row["future_return"] for row in predictions if row["score"] <= low_cut]
    report = {
        "status": "completed",
        "data_source": "user_supplied_csv",
        "input_file": path.name,
        "symbols": sorted(grouped),
        "input_rows": sum(len(rows) for rows in grouped.values()),
        "evaluated_observations": len(predictions),
        "lookback_window": window,
        "forward_horizon_rows": horizon,
        "metrics": {
            "mean_future_return": mean_outcome,
            "score_future_return_pearson_correlation": correlation,
            "top_quartile_mean_future_return": statistics.mean(high) if high else None,
            "bottom_quartile_mean_future_return": statistics.mean(low) if low else None,
            "top_minus_bottom_quartile_return": (statistics.mean(high) - statistics.mean(low)) if high and low else None,
            "positive_future_return_rate": sum(value > 0 for value in outcomes) / len(outcomes),
        },
        "analyzers": {
            name: {
                "observations": values["count"],
                "mean_score": values["score_sum"] / values["count"] if values["count"] else None,
                "unavailable_rate": values["unavailable"] / values["count"] if values["count"] else None,
            }
            for name, values in sorted(analyzer_totals.items())
        },
        "limitations": [
            "This is a diagnostic, not proof of predictive edge or profitability.",
            "Scores and outcomes are overlapping time-series observations; significance testing is not included.",
            "Trading costs, spread, slippage, corporate actions, and session effects are not modeled.",
            "Volatility and momentum definitions must be confirmed against the live data producer before interpreting results.",
        ],
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path, help="Real OHLCV CSV; no synthetic fallback")
    parser.add_argument("--window", type=int, default=20, help="Trailing rows used for indicators (default: 20)")
    parser.add_argument("--horizon", type=int, default=5, help="Rows ahead used to score outcomes (default: 5)")
    parser.add_argument("--output", type=Path, default=Path("level_01_historical_report.json"))
    args = parser.parse_args()
    report = evaluate(args.csv, args.window, args.horizon)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"LEVEL_01_HISTORICAL_REPORT={args.output}")


if __name__ == "__main__":
    main()
