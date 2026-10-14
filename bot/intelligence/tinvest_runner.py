from __future__ import annotations

import os

from bot.intelligence.integration import build_market_snapshot
from bot.intelligence.levels.level_04.historical_backtest import evaluate_pressure_history
from bot.intelligence.pipeline.intelligence_pipeline import IntelligencePipeline
from bot.live_runner import LiveMarketRunner
from bot.tinvest_client import TInvestClient
from bot.virtual_portfolio import VirtualPortfolio


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
    # CI smoke runs do not have access to the bot's persistent local portfolio.
    # Supply a known-empty diagnostic portfolio rather than letting L9 confuse
    # missing portfolio context with a real zero-position portfolio.
    diagnostic_portfolio = VirtualPortfolio(initial_balance=10_000.0)
    results = []
    for analysis in scan.buy_candidates[:limit]:
        current_price = scan.current_prices.get(analysis.ticker)
        if current_price is None or scan.previous_closes.get(analysis.ticker) is None:
            continue

        # Use the same full-context integration as the bot's main scan path:
        # market breadth/return, sector and peer history, aligned return series,
        # and current portfolio holdings must reach the live Intelligence run.
        snapshot = build_market_snapshot(scan, analysis, portfolio=diagnostic_portfolio)
        if snapshot is None:
            continue
        intelligence = pipeline.analyze(snapshot)
        historical_candles = getattr(scan, "candle_history", {}).get(analysis.ticker, ())
        backtest = evaluate_pressure_history(
            historical_candles,
            symbol=analysis.ticker,
            horizons=(1, 3, 5),
            signal_threshold=0.65,
            round_trip_cost=0.001,
        )
        results.append((analysis, intelligence, current_price, backtest))

    return results


def main() -> None:
    token = os.getenv("INVEST_TOKEN", "").strip()
    results = run_real_market_intelligence(token)

    if not results:
        raise RuntimeError("No instruments were successfully analyzed")

    print("REAL T-INVEST MARKET DATA + INTELLIGENCE (READ-ONLY)")
    print(f"Analyzed instruments: {len(results)}")
    print("Portfolio context: empty diagnostic paper portfolio (persistent bot portfolio is not available in CI)")
    print("Level 4 historical pressure evaluation: closed candles only; forward outcomes are scored separately")
    print("-" * 72)

    for analysis, result, current_price, backtest in results:
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
        print(f"  L4 backtest: bars={backtest['bars']} signals={backtest['signals']}")
        for metric, values in backtest["summary"].items():
            if values["count"]:
                win_rate = values["win_rate_after_costs"]
                mean_return = values["mean_net_directional_return"]
                print(
                    f"    {metric}: n={values['count']} "
                    f"win_after_costs={win_rate:.1%} "
                    f"mean_net_directional_return={mean_return:+.3%}"
                )
        if not backtest["signals"]:
            print("    L4 backtest unavailable: no qualifying historical signals")
        if backtest["warnings"]:
            print(f"    L4 backtest warnings: {'; '.join(backtest['warnings'][:3])}")

    print("-" * 72)
    print("Trade execution: DISABLED")
    print("Decision Engine: NOT CONNECTED")


if __name__ == "__main__":
    main()
