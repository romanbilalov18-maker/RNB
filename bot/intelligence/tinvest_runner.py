from __future__ import annotations

import os

from bot.intelligence.integration import build_market_snapshot
from bot.intelligence.pipeline.intelligence_pipeline import IntelligencePipeline
from bot.live_runner import LiveMarketRunner
from bot.tinvest_client import TInvestClient


def run_real_market_intelligence(token: str, limit: int = 10) -> list:
    if not token.strip():
        raise ValueError("T-Invest token is required")
    if limit <= 0:
        raise ValueError("limit must be positive")

    # Read-only: LiveMarketRunner only requests market data and candles.
    client = TInvestClient(token)
    with client._client() as raw_client:
        market_runner = LiveMarketRunner(raw_client, history_days=30)
        scan = market_runner.run()

    pipeline = IntelligencePipeline()
    results = []
    for analysis in scan.buy_candidates[:limit]:
        current_price = scan.current_prices.get(analysis.ticker)
        if current_price is None or scan.previous_closes.get(analysis.ticker) is None:
            continue

        # Use the same full-context integration as the bot's main scan path:
        # market breadth/return, sector and peer history, aligned return series,
        # and current portfolio holdings must reach the live Intelligence run.
        snapshot = build_market_snapshot(scan, analysis)
        if snapshot is None:
            continue
        intelligence = pipeline.analyze(snapshot)
        results.append((analysis, intelligence, current_price))

    return results


def main() -> None:
    token = os.getenv("INVEST_TOKEN", "").strip()
    results = run_real_market_intelligence(token)

    if not results:
        raise RuntimeError("No instruments were successfully analyzed")

    print("REAL T-INVEST MARKET DATA + INTELLIGENCE (READ-ONLY)")
    print(f"Analyzed instruments: {len(results)}")
    print("-" * 72)

    for analysis, result, current_price in results:
        snapshot = result.level_01
        print(
            f"{analysis.ticker}: "
            f"price={current_price:.4f} "
            f"daily_change={snapshot.analyzer_results[0].metrics.get('change', 0.0):+.4%} "
            f"intelligence={result.overall_score:.4f} "
            f"confidence={result.overall_confidence:.4f} "
            f"consistency={result.overall_consistency:.4f}"
        )
        level_confidences = sorted(
            (
                (number, float(getattr(result, f"level_{number:02d}").confidence))
                for number in range(1, 16)
            ),
            key=lambda item: item[1],
        )
        bottlenecks = ", ".join(
            f"L{number}={confidence:.3f}"
            for number, confidence in level_confidences[:3]
        )
        print(f"  confidence_bottlenecks: {bottlenecks}")
        if result.warnings:
            print(f"  warnings: {'; '.join(result.warnings[:5])}")

    print("-" * 72)
    print("Trade execution: DISABLED")
    print("Decision Engine: NOT CONNECTED")


if __name__ == "__main__":
    main()
