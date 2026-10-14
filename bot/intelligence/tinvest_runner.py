from __future__ import annotations

import os

from bot.intelligence.integration import build_market_snapshot
from bot.intelligence.levels.level_04.historical_backtest import (
    build_market_regime_by_date,
    evaluate_pressure_history,
    evaluate_pressure_rolling_walk_forward,
    evaluate_pressure_walk_forward,
)
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
        market_runner = LiveMarketRunner(raw_client, history_days=180)
        scan = market_runner.run()

    pipeline = IntelligencePipeline()
    # CI smoke runs do not have access to the bot's persistent local portfolio.
    # Supply a known-empty diagnostic portfolio rather than letting L9 confuse
    # missing portfolio context with a real zero-position portfolio.
    diagnostic_portfolio = VirtualPortfolio(initial_balance=10_000.0)
    results = []
    market_regimes = build_market_regime_by_date(getattr(scan, "candle_history", {}))
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
            market_regime_by_date=market_regimes,
        )
        walk_forward = evaluate_pressure_walk_forward(
            historical_candles,
            symbol=analysis.ticker,
            horizons=(1, 3, 5),
            signal_threshold=0.65,
            round_trip_cost=0.001,
            train_fraction=0.70,
            market_regime_by_date=market_regimes,
        )
        rolling_walk_forward = evaluate_pressure_rolling_walk_forward(
            historical_candles,
            symbol=analysis.ticker,
            horizons=(1, 3, 5),
            round_trip_cost=0.001,
            train_fraction=0.50,
            holdout_fraction=0.20,
            step_fraction=0.15,
            market_regime_by_date=market_regimes,
        )
        results.append((analysis, intelligence, current_price, backtest, walk_forward, rolling_walk_forward))

    return results


def main() -> None:
    token = os.getenv("INVEST_TOKEN", "").strip()
    results = run_real_market_intelligence(token)

    if not results:
        raise RuntimeError("No instruments were successfully analyzed")

    print("REAL T-INVEST MARKET DATA + INTELLIGENCE (READ-ONLY)")
    print(f"Analyzed instruments: {len(results)}")
    print("Portfolio context: empty diagnostic paper portfolio (persistent bot portfolio is not available in CI)")
    print("Level 4 evaluation: training-only threshold selection; fixed and rolling chronological holdouts")
    print("-" * 72)

    for analysis, result, current_price, backtest, walk_forward, rolling_walk_forward in results:
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
        print(
            f"  L4 threshold selection: baseline={walk_forward['baseline_threshold']:.2f} "
            f"selected={walk_forward['selected_threshold']:.2f} "
            f"train_score={walk_forward['threshold_selection']['selected_threshold_score']}"
        )
        if walk_forward["threshold_selection"]["fallback_used"]:
            print("    threshold selection fallback: insufficient training outcomes")
        train_count = len(walk_forward["train"]["outcomes"])
        holdout_count = len(walk_forward["holdout"]["outcomes"])
        print(
            f"  L4 walk-forward: split={walk_forward['split_date']} "
            f"train_outcomes={train_count} holdout_outcomes={holdout_count}"
        )
        for metric, values in walk_forward["holdout"]["summary"].items():
            if values["count"]:
                mean_net = values["mean_net_directional_return"]
                print(
                    f"    holdout {metric}: n={values['count']} "
                    f"win_after_costs={values['win_rate_after_costs']:.1%} "
                    f"mean_net_directional_return={mean_net:+.3%}"
                )
        if walk_forward["warnings"]:
            print(f"    L4 walk-forward warnings: {'; '.join(walk_forward['warnings'][:2])}")
        rolling_metrics = rolling_walk_forward["aggregate"]
        baseline_metrics = rolling_walk_forward.get("baseline_aggregate", {})
        print(
            f"  L4 rolling walk-forward: windows={len(rolling_walk_forward['windows'])} "
            f"selected_n={rolling_metrics['count']} "
            f"selected_net={rolling_metrics['mean_net_directional_return']} "
            f"baseline_n={baseline_metrics.get('count')} "
            f"baseline_net={baseline_metrics.get('mean_net_directional_return')}"
        )
        if rolling_walk_forward["warnings"]:
            print(f"    L4 rolling warnings: {'; '.join(rolling_walk_forward['warnings'][:2])}")

    print("-" * 72)
    print("L4 HISTORICAL PRESSURE SUMMARY ACROSS SCANNED INSTRUMENTS")
    for signal in ("BUY_PRESSURE", "SELL_PRESSURE"):
        for horizon in (1, 3, 5):
            observations = [
                outcome
                for _, _, _, backtest, _, _ in results
                for outcome in backtest["outcomes"]
                if outcome["signal"] == signal and outcome["horizon"] == horizon
            ]
            if not observations:
                print(f"  {signal} h{horizon}: insufficient qualifying signals")
                continue
            win_rate = sum(item["correct_after_costs"] for item in observations) / len(observations)
            mean_forward = sum(item["forward_return"] for item in observations) / len(observations)
            mean_net = sum(item["net_forward_return"] for item in observations) / len(observations)
            print(
                f"  {signal} h{horizon}: n={len(observations)} "
                f"win_after_costs={win_rate:.1%} "
                f"mean_forward_return={mean_forward:+.3%} "
                f"mean_net_directional_return={mean_net:+.3%}"
            )
    print("-" * 72)
    print("L4 WALK-FORWARD HOLDOUT SUMMARY (UNSEEN CHRONOLOGICAL PERIOD)")
    holdout_outcomes = [
        outcome
        for _, _, _, _, walk_forward, _ in results
        for outcome in walk_forward["holdout"]["outcomes"]
    ]
    regimes = sorted({item["market_regime"] for item in holdout_outcomes}) or ["UNCLASSIFIED"]
    for signal in ("BUY_PRESSURE", "SELL_PRESSURE"):
        for horizon in (1, 3, 5):
            for regime in regimes:
                observations = [
                    item for item in holdout_outcomes
                    if item["signal"] == signal and item["horizon"] == horizon
                    and item["market_regime"] == regime
                ]
                if not observations:
                    continue
                win_rate = sum(item["correct_after_costs"] for item in observations) / len(observations)
                mean_net = sum(item["net_forward_return"] for item in observations) / len(observations)
                print(
                    f"  {signal} h{horizon} {regime}: n={len(observations)} "
                    f"win_after_costs={win_rate:.1%} mean_net_directional_return={mean_net:+.3%}"
                )
    selected_holdout = holdout_outcomes
    baseline_holdout = [
        item
        for _, _, _, _, walk_forward in results
        for item in walk_forward["baseline_holdout"]["outcomes"]
    ]
    for label, observations in (("selected", selected_holdout), ("baseline_0.65", baseline_holdout)):
        if observations:
            win_rate = sum(item["correct_after_costs"] for item in observations) / len(observations)
            mean_net = sum(item["net_forward_return"] for item in observations) / len(observations)
            print(
                f"  aggregate {label}: n={len(observations)} "
                f"win_after_costs={win_rate:.1%} mean_net_directional_return={mean_net:+.3%}"
            )
    print("  Threshold is selected on training outcomes only; holdout is comparison-only.")
    print("  Training-period outcomes are descriptive only; no model weights are trained or changed.")
    print("  Training outcomes end before the split; holdout signals start on/after the split.")
    rolling_selected = [
        item for _, _, _, _, _, rolling in results
        for window in rolling["windows"] for item in window["selected_outcomes"]
    ]
    rolling_baseline = [
        item for _, _, _, _, _, rolling in results
        for window in rolling["windows"] for item in window["baseline_outcomes"]
    ]
    for label, observations in (("rolling_selected", rolling_selected), ("rolling_baseline_0.65", rolling_baseline)):
        if observations:
            win_rate = sum(item["correct_after_costs"] for item in observations) / len(observations)
            mean_net = sum(item["net_forward_return"] for item in observations) / len(observations)
            print(
                f"  aggregate {label}: n={len(observations)} "
                f"win_after_costs={win_rate:.1%} mean_net_directional_return={mean_net:+.3%}"
            )
    print("  Results are exploratory and do not authorize automatic weight changes.")
    print("-" * 72)
    print("Trade execution: DISABLED")
    print("Decision Engine: NOT CONNECTED")


if __name__ == "__main__":
    main()
