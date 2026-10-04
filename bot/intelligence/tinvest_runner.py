from __future__ import annotations

import os

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.pipeline.intelligence_pipeline import IntelligencePipeline
from bot.live_runner import LiveMarketRunner
from bot.tinvest_client import TInvestClient


def _quotation(value: object) -> float:
    units = getattr(value, "units", None)
    nano = getattr(value, "nano", None)
    if units is None:
        return float(value)
    return float(units) + float(nano or 0) / 1_000_000_000


def _build_snapshot(
    analysis,
    current_price: float,
    previous_close: float,
    lot_size: int,
    latest_candle: object | None = None,
) -> MarketSnapshot:
    liquidity = min(max(analysis.volume_ratio / 2.0, 0.0), 1.0)

    open_price = high_price = low_price = close_price = None
    candle_volume = None
    candle_range = None
    close_position = None
    volume_ratio = None

    if latest_candle is not None:
        open_price = _quotation(getattr(latest_candle, "open"))
        high_price = _quotation(getattr(latest_candle, "high"))
        low_price = _quotation(getattr(latest_candle, "low"))
        close_price = _quotation(getattr(latest_candle, "close"))
        candle_volume = float(getattr(latest_candle, "volume", 0) or 0)

        if close_price > 0 and high_price >= low_price:
            candle_range = (high_price - low_price) / close_price

        if high_price > low_price:
            close_position = (close_price - low_price) / (high_price - low_price)

        if analysis.average_volume > 0 and candle_volume >= 0:
            volume_ratio = candle_volume / analysis.average_volume

    return MarketSnapshot(
        symbol=analysis.ticker,
        price=current_price,
        previous_price=previous_close,
        volume=candle_volume,
        average_volume=analysis.average_volume,
        volatility=analysis.volatility,
        momentum=analysis.momentum,
        liquidity=liquidity,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        candle_volume=candle_volume,
        average_candle_volume=analysis.average_volume,
        candle_range=candle_range,
        close_position=close_position,
        volume_ratio=volume_ratio,
        lot_size=lot_size,
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
        previous_close = scan.previous_closes.get(analysis.ticker)
        if previous_close is None:
            continue
        snapshot = _build_snapshot(
            analysis,
            current_price,
            previous_close,
            scan.lot_sizes.get(analysis.ticker, 1),
            scan.latest_candles.get(analysis.ticker),
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
        snapshot = result.level_01
        print(
            f"{analysis.ticker}: "
            f"price={current_price:.4f} "
            f"daily_change={snapshot.analyzer_results[0].metrics.get('change', 0.0):+.4%} "
            f"intelligence={result.overall_score:.4f} "
            f"confidence={result.overall_confidence:.4f} "
            f"consistency={result.overall_consistency:.4f}"
        )

    print("-" * 72)
    print("Trade execution: DISABLED")
    print("Decision Engine: NOT CONNECTED")


if __name__ == "__main__":
    main()
