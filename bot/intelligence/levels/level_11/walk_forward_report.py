"""Generate a chronological holdout report for L11 learning observations.

Run:
    python -m bot.intelligence.levels.level_11.walk_forward_report --database data/decision_audit.sqlite
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bot.decision_audit import DecisionAuditStore
from bot.intelligence.levels.level_11.analyzers.walk_forward_validation import evaluate_multiple_windows, evaluate_walk_forward


def build_report(database: str | Path, train_fraction: float = 0.6) -> dict:
    store = DecisionAuditStore(database)
    observations_by_ticker = store.learning_observations_by_ticker()
    ticker_reports = {
        ticker: {
            "single_holdout": evaluate_walk_forward(observations, train_fraction=train_fraction),
            "multiple_windows": evaluate_multiple_windows(observations),
        }
        for ticker, observations in sorted(observations_by_ticker.items())
    }
    evaluated = {
        ticker: report for ticker, report in ticker_reports.items()
        if report["single_holdout"].get("status") == "evaluated"
    }
    multi_window_evaluated = {
        ticker: report for ticker, report in ticker_reports.items()
        if report["multiple_windows"].get("status") == "evaluated"
    }
    return {
        "database": str(database),
        "train_fraction": train_fraction,
        "ticker_count": len(ticker_reports),
        "evaluated_ticker_count": len(evaluated),
        "multiple_window_evaluated_ticker_count": len(multi_window_evaluated),
        "tickers": ticker_reports,
        "deployment_allowed": False,
        "deployment_note": (
            "This report is diagnostic only. Do not apply weights unless multiple chronological "
            "holdout windows and realistic transaction-cost-aware backtests confirm improvement."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate L11 proposed weights on chronological holdout data.")
    parser.add_argument("--database", required=True, help="Path to decision_audit.sqlite")
    parser.add_argument("--train-fraction", type=float, default=0.6)
    parser.add_argument("--output", help="Optional JSON output path; defaults to stdout")
    args = parser.parse_args()
    report = build_report(args.database, train_fraction=args.train_fraction)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
