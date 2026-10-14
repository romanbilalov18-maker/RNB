from __future__ import annotations

import os

from bot.intelligence.integration import build_market_snapshot
from bot.intelligence.levels.level_04.historical_backtest import (
    build_market_regime_by_date,
    evaluate_pressure_history,
    evaluate_pressure_rolling_walk_forward,
    evaluate_pressure_walk_forward,
)
from bot.intelligence.levels.level_06.historical_risk_backtest import evaluate_level6_risk_history
from bot.intelligence.levels.level_12.historical_anomaly_backtest import evaluate_level12_anomaly_history, compare_level_combinations
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
        risk_backtest = evaluate_level6_risk_history(
            historical_candles, symbol=analysis.ticker, horizons=(1, 3, 5), lookback=20,
        )
        anomaly_backtest = evaluate_level12_anomaly_history(
            historical_candles, symbol=analysis.ticker, horizons=(1, 3, 5),
            lookback=20, adverse_move_threshold=0.02, anomaly_score_threshold=0.50,
        )
        anomaly_backtest["combination_comparison"] = compare_level_combinations(
            backtest, risk_backtest, anomaly_backtest, alert_threshold=0.65,
        )
        results.append((analysis, intelligence, current_price, backtest, walk_forward, rolling_walk_forward, risk_backtest, anomaly_backtest))

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

    for analysis, result, current_price, backtest, walk_forward, rolling_walk_forward, risk_backtest, anomaly_backtest in results:
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
        print(f"  L6 risk validation: bars={risk_backtest['bars']} outcomes={len(risk_backtest['outcomes'])}")
        for metric, values in risk_backtest["summary"].items():
            print(
                f"    {metric}: n={values['count']} "
                f"downside_drawdown_corr={values['downside_score_drawdown_correlation']} "
                f"volatility_realized_corr={values['volatility_score_realized_volatility_correlation']}"
            )
        if risk_backtest["warnings"]:
            print(f"    L6 risk warnings: {'; '.join(risk_backtest['warnings'][:2])}")
        print(f"  L12 anomaly validation: bars={anomaly_backtest['bars']} outcomes={len(anomaly_backtest['outcomes'])}")
        for metric, values in anomaly_backtest["summary"].items():
            print(
                f"    {metric}: n={values['count']} event_rate={values['adverse_event_rate']} "
                f"score_event_corr={values['anomaly_adverse_move_correlation']} "
                f"top_quartile_lift={values['top_quartile_event_rate_lift']} "
                f"precision={values['threshold_metrics']['precision']} "
                f"recall={values['threshold_metrics']['recall']}"
            )
        if anomaly_backtest["warnings"]:
            print(f"    L12 anomaly warnings: {'; '.join(anomaly_backtest['warnings'][:2])}")
        print("  L4/L6/L12 same-date alert comparison:")
        for metric, values in anomaly_backtest["combination_comparison"]["summary"].items():
            print(f"    {metric}: observations={values['count']}")
            for variant, stats in values["variants"].items():
                print(
                    f"      {variant}: alerts={stats.get('alert_count', 0)} "
                    f"precision={stats['precision']} recall={stats['recall']} "
                    f"false_positive_rate={stats['false_positive_rate']} lift={stats['lift']}"
                )
                trade = stats["trading_filter"]
                print(
                    f"        after_cost_filter: n={trade['eligible_trades']} "
                    f"coverage={trade['coverage']} mean_net={trade['mean_net_return']} "
                    f"compounded_net={trade['compounded_net_return']} "
                    f"win_rate={trade['win_rate_after_costs']} "
                    f"max_drawdown={trade['max_drawdown_sequential']}"
                )
        reference = values["all_dates_reference"]
        print(
            f"      all_dates_reference: mean_net={reference['mean_net_return']} "
            f"compounded_net={reference['compounded_net_return']} "
            f"win_rate={reference['win_rate_after_costs']} "
            f"max_drawdown={reference['max_drawdown_sequential']}"
        )
        holdout = anomaly_backtest["combination_comparison"]["chronological_holdout"]
        print(
            f"  L4/L6/L12 chronological holdout: split={holdout['split_date']} "
            f"train={holdout['train_count']} holdout={holdout['holdout_count']}"
        )
        for metric, values in holdout["holdout"].items():
            print(f"    HOLDOUT {metric}: observations={values['count']}")
            for variant, stats in values["variants"].items():
                print(
                    f"      {variant}: alerts={stats.get('alert_count', 0)} "
                    f"precision={stats['precision']} recall={stats['recall']} "
                    f"false_positive_rate={stats['false_positive_rate']} lift={stats['lift']}"
                )
        for symbol, symbol_summary in anomaly_backtest["combination_comparison"]["by_symbol"].items():
            for metric, values in symbol_summary.items():
                variants = values["variants"]
                print(
                    f"  INSTRUMENT {symbol} {metric}: n={values['count']} "
                    f"L4_lift={variants['l4_alert']['lift']} "
                    f"L4_L12_lift={variants['l4_l12_alert']['lift']} "
                    f"L4_L6_L12_lift={variants['l4_l6_l12_alert']['lift']}"
                )

    print("-" * 72)
    print("L4 HISTORICAL PRESSURE SUMMARY ACROSS SCANNED INSTRUMENTS")
    for signal in ("BUY_PRESSURE", "SELL_PRESSURE"):
        for horizon in (1, 3, 5):
            observations = [
                outcome
                for _, _, _, backtest, _, _, _, _ in results
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
        for _, _, _, _, walk_forward, _, _, _ in results
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
        for _, _, _, _, walk_forward, _, _, _ in results
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
        item for _, _, _, _, _, rolling, _, _ in results
        for window in rolling["windows"] for item in window["selected_outcomes"]
    ]
    rolling_baseline = [
        item for _, _, _, _, _, rolling, _, _ in results
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
    risk_outcomes = [item for _, _, _, _, _, _, risk, _ in results for item in risk["outcomes"]]
    print("L6 RISK VALIDATION SUMMARY")
    from bot.intelligence.levels.level_06.historical_risk_backtest import _correlation
    for horizon in (1, 3, 5):
        observations = [item for item in risk_outcomes if item["horizon"] == horizon]
        if not observations:
            print(f"  h{horizon}: insufficient observations")
            continue
        print(
            f"  h{horizon}: n={len(observations)} "
            f"downside_drawdown_corr={_correlation([x['downside_risk_score'] for x in observations], [x['realized_max_drawdown'] for x in observations])} "
            f"volatility_realized_corr={_correlation([x['volatility_risk_score'] for x in observations], [x['realized_volatility'] for x in observations])}"
        )
    print("  Risk scores are diagnostic; no weights or trade rules are changed.")
    anomaly_outcomes = [item for _, _, _, _, _, _, _, anomaly in results for item in anomaly["outcomes"]]
    print("L12 ANOMALY VALIDATION SUMMARY")
    from bot.intelligence.levels.level_12.historical_anomaly_backtest import _binary_metrics, _correlation
    for horizon in (1, 3, 5):
        observations = [item for item in anomaly_outcomes if item["horizon"] == horizon]
        if not observations:
            print(f"  h{horizon}: insufficient observations")
            continue
        scores = [item["anomaly_score"] for item in observations]
        moves = [item["realized_adverse_move"] for item in observations]
        event_rate = sum(item["adverse_event"] for item in observations) / len(observations)
        top_cutoff = sorted(scores)[max(0, int(0.75 * len(scores)) - 1)]
        top = [item for item in observations if item["anomaly_score"] >= top_cutoff]
        top_rate = sum(item["adverse_event"] for item in top) / len(top) if top else None
        print(
            f"  h{horizon}: n={len(observations)} event_rate={event_rate:.1%} "
            f"score_event_corr={_correlation(scores, moves)} "
            f"top_quartile_event_rate={top_rate} "
            f"top_quartile_lift={top_rate / event_rate if top_rate is not None and event_rate else None} "
            f"threshold_metrics={_binary_metrics(observations, 0.50)}"
        )
    print("  Anomaly scores are diagnostic; no weights or trade rules are changed.")
    print("L4/L6/L12 COMBINATION SUMMARY (SAME DATES)")
    combination_rows = [
        row for _, _, _, _, _, _, _, anomaly in results
        for row in anomaly["combination_comparison"]["outcomes"]
    ]
    print("L4/L6/L12 CHRONOLOGICAL HOLDOUT SUMMARY")
    holdout_rows = [
        row for _, _, _, _, _, _, _, anomaly in results
        for row in anomaly["combination_comparison"]["outcomes"]
        if anomaly["combination_comparison"]["chronological_holdout"]["split_date"] is not None
        and row["signal_date"] >= anomaly["combination_comparison"]["chronological_holdout"]["split_date"]
    ]
    for horizon in (1, 3, 5):
        rows = [row for row in holdout_rows if row["horizon"] == horizon]
        if not rows:
            print(f"  h{horizon}: insufficient holdout observations")
            continue
        event_count = sum(row["event"] for row in rows)
        event_rate = event_count / len(rows)
        print(f"  HOLDOUT h{horizon}: n={len(rows)} event_rate={event_rate:.1%}")
        for variant in ("l4_alert", "l4_l6_alert", "l4_l12_alert", "l4_l6_l12_alert"):
            alerts = [row for row in rows if row[variant]]
            tp = sum(row["event"] for row in alerts)
            fp = len(alerts) - tp
            negatives = len(rows) - event_count
            precision = tp / len(alerts) if alerts else None
            recall = tp / event_count if event_count else None
            fpr = fp / negatives if negatives else None
            lift = precision / event_rate if precision is not None and event_rate else None
            print(f"    {variant}: alerts={len(alerts)} precision={precision} recall={recall} fpr={fpr} lift={lift}")
            eligible = [row for row in rows if not row[variant]]
            net_returns = [row["forward_return"] - 0.001 for row in eligible]
            baseline_returns = [row["forward_return"] - 0.001 for row in rows]
            mean_net = sum(net_returns) / len(net_returns) if net_returns else None
            baseline_mean = sum(baseline_returns) / len(baseline_returns) if baseline_returns else None
            print(
                f"      after_cost_filter: n={len(eligible)} "
                f"coverage={len(eligible)/len(rows):.1%} mean_net={mean_net} "
                f"baseline_mean_net={baseline_mean}"
            )
    for horizon in (1, 3, 5):
        rows = [row for row in combination_rows if row["horizon"] == horizon]
        if not rows:
            print(f"  h{horizon}: insufficient observations")
            continue
        event_count = sum(row["event"] for row in rows)
        event_rate = event_count / len(rows)
        print(f"  h{horizon}: n={len(rows)} adverse_event_rate={event_rate:.1%}")
        for variant in ("l4_alert", "l4_l6_alert", "l4_l12_alert", "l4_l6_l12_alert"):
            alerts = [row for row in rows if row[variant]]
            true_positive = sum(row["event"] for row in alerts)
            negatives = len(rows) - event_count
            false_positive = len(alerts) - true_positive
            precision = true_positive / len(alerts) if alerts else None
            recall = true_positive / event_count if event_count else None
            fpr = false_positive / negatives if negatives else None
            lift = precision / event_rate if precision is not None and event_rate > 0 else None
            print(
                f"    {variant}: alerts={len(alerts)} precision={precision} "
                f"recall={recall} false_positive_rate={fpr} lift={lift}"
            )
    print("  Returns subtract a 0.10% round-trip cost per eligible observation.")
    print("  Overlapping horizons are not independent; compounded values are diagnostic, not portfolio backtest P&L.")
    print("  Same-date alert comparison is diagnostic only; no weights or trade rules changed.")
    print("  Results are exploratory and do not authorize automatic weight changes.")
    print("-" * 72)
    print("Trade execution: DISABLED")
    print("Decision Engine: NOT CONNECTED")


if __name__ == "__main__":
    main()
