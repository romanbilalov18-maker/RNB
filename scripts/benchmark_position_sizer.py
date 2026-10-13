"""Measure PositionSizer scaling without risking a long-running benchmark.

Run: python scripts/benchmark_position_sizer.py
Each candidate count runs in an isolated subprocess with a timeout, so a
combinatorial slowdown cannot hang the whole benchmark.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_COUNTS = (3, 4, 5, 8, 10)
TIMEOUT_SECONDS = 5


def run_case(count: int) -> dict:
    # Python puts scripts/ on sys.path when this file is executed directly.
    # Add the repository root so isolated workers can import the bot package.
    sys.path.insert(0, str(REPOSITORY_ROOT))

    analyses = [
        SimpleNamespace(ticker=f"T{i:02}", volatility=0.01 + i * 0.001)
        for i in range(count)
    ]
    prices = {item.ticker: 100.0 for item in analyses}
    lot_sizes = {item.ticker: 1 for item in analyses}

    from bot.position_sizer import PositionSizer

    started = time.perf_counter()
    plans = PositionSizer(commission_rate=0.001).plan(
        cash=10_000.0,
        analyses=analyses,
        prices=prices,
        lot_sizes=lot_sizes,
    )
    return {
        "candidates": count,
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "plans": len(plans),
        "status": "completed",
    }


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        print(json.dumps(run_case(int(sys.argv[2]))))
        return 0

    print("PositionSizer benchmark (5-second timeout per case)")
    failed = False
    for count in CANDIDATE_COUNTS:
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                [sys.executable, __file__, "--worker", str(count)],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                check=False,
                cwd=REPOSITORY_ROOT,
            )
        except subprocess.TimeoutExpired:
            failed = True
            print(json.dumps({
                "candidates": count,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "status": f"timeout_after_{TIMEOUT_SECONDS}s",
            }))
            continue

        if completed.returncode == 0:
            print(completed.stdout.strip())
        else:
            failed = True
            print(json.dumps({
                "candidates": count,
                "status": "error",
                "returncode": completed.returncode,
                "stderr": completed.stderr[-1000:],
            }))
    if failed:
        print("ERROR: one or more benchmark cases failed or timed out.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
