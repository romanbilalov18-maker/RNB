from __future__ import annotations

import os

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.pipeline.intelligence_pipeline import IntelligencePipeline
from bot.live_runner import LiveMarketRunner
from bot.tinvest_client import TInvestClient


def _build_snapshot(analysis, current_price: float, lot_size: int) -> MarketSnapshot:
    previous_price = analysis.last_price
    liquidity = min(max(analysis.volume_ratio / 2.0, 0.0), 1.0)
    return MarketSnapshot(
        symbol=analysis.ticker,
        price=current_price,
        previous_price=previous_price,
        volume=analysis.average_volume * analysis.volume_ratio,
        average_volume=analysis.average_volume,
        volatility=analysis.volatility,
        momentum=analysis.momentum,
        liquidity=liquidity,
    )


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
        if current_price is None:
            continue
        snapshot = _build_snapshot(
            analysis,
            current_price,
            scan.lot_sizes.get(analysis.ticker, 1),
        )
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
        print(
            f"{analysis.ticker}: "
            f"price={current_price:.4f} "
            f"daily_change={result.level_01.analyzer_results[0].metrics.get('change', 0.0):+.4%} "
            f"intelligence={result.overall_score:.4f} "
            f"confidence={result.overall_confidence:.4f} "
            f"consistency={result.overall_consistency:.4f}"
        )

    print("-" * 72)
    print("Trade execution: DISABLED")
    print("Decision Engine: NOT CONNECTED")


if __name__ == "__main__":
    main()
