"""Leakage-safe historical evaluation of Level 12 anomaly scores."""
from __future__ import annotations

from math import isfinite, sqrt
from statistics import fmean, pstdev
from typing import Iterable

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.pipeline.intelligence_pipeline import IntelligencePipeline


def _number(value) -> float | None:
    if value is None:
        return None
    units, nano = getattr(value, "units", None), getattr(value, "nano", None)
    try:
        result = float(units) + float(nano or 0) / 1_000_000_000 if units is not None else float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) else None


def _date(candle, index: int) -> str:
    value = getattr(candle, "time", None) or getattr(candle, "date", None)
    return value.isoformat() if hasattr(value, "isoformat") else str(value if value is not None else index)


def _correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean, right_mean = fmean(left), fmean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = sqrt(
        sum((x - left_mean) ** 2 for x in left)
        * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator if denominator > 0 else None


def _binary_metrics(items: list[dict], threshold: float) -> dict:
    predicted = [item for item in items if item["anomaly_score"] >= threshold]
    true_positive = sum(item["adverse_event"] for item in predicted)
    false_positive = len(predicted) - true_positive
    false_negative = sum(item["adverse_event"] for item in items if item["anomaly_score"] < threshold)
    event_count = sum(item["adverse_event"] for item in items)
    return {
        "count": len(items),
        "predicted_count": len(predicted),
        "event_rate": event_count / len(items) if items else None,
        "precision": true_positive / len(predicted) if predicted else None,
        "recall": true_positive / event_count if event_count else None,
        "false_positive_rate": (
            false_positive / (len(items) - event_count)
            if len(items) > event_count else None
        ),
    }


def evaluate_level12_anomaly_history(
    candles: Iterable[object],
    *,
    symbol: str = "UNKNOWN",
    horizons: tuple[int, ...] = (1, 3, 5),
    lookback: int = 20,
    adverse_move_threshold: float = 0.02,
    anomaly_score_threshold: float = 0.50,
) -> dict:
    """Evaluate whether L12 anomaly scores precede subsequent downside events.

    Every historical snapshot is calculated only from candles available on its
    decision date. Future candles contribute only to adverse-event labels.
    A positive event means at least one future close falls by the configured
    fraction from the decision close. This is diagnostic, not a trade signal.
    """
    if not horizons or any(not isinstance(h, int) or h < 1 for h in horizons):
        raise ValueError("horizons must contain positive integers")
    if lookback < 5:
        raise ValueError("lookback must be at least 5")
    if not isfinite(adverse_move_threshold) or not 0.0 < adverse_move_threshold < 1.0:
        raise ValueError("adverse_move_threshold must be between 0 and 1")
    if not isfinite(anomaly_score_threshold) or not 0.0 <= anomaly_score_threshold <= 1.0:
        raise ValueError("anomaly_score_threshold must be between 0 and 1")

    bars = []
    for index, candle in enumerate(candles or ()):
        close = _number(getattr(candle, "close", None))
        if close is None or close <= 0:
            continue
        bars.append({
            "date": _date(candle, index),
            "open": _number(getattr(candle, "open", None)),
            "high": _number(getattr(candle, "high", None)),
            "low": _number(getattr(candle, "low", None)),
            "close": close,
            "volume": _number(getattr(candle, "volume", None)),
        })
    bars.sort(key=lambda item: item["date"])
    max_horizon = max(horizons)
    if len(bars) < lookback + max_horizon + 2:
        return {
            "symbol": symbol, "bars": len(bars), "outcomes": [], "summary": {},
            "warnings": ["level12_anomaly_history_insufficient"],
            "methodology": {"lookahead": False, "snapshot_uses_past_only": True},
        }

    pipeline = IntelligencePipeline()
    outcomes = []
    for i in range(lookback, len(bars) - max_horizon):
        history = bars[max(0, i - lookback):i + 1]
        returns = tuple(
            history[j]["close"] / history[j - 1]["close"] - 1.0
            for j in range(1, len(history)) if history[j - 1]["close"] > 0
        )
        if len(returns) < 2:
            continue
        current = bars[i]
        previous = bars[i - 1]
        volatility = pstdev(returns)
        momentum = current["close"] / bars[max(0, i - 5)]["close"] - 1.0
        volumes = [
            item["volume"] for item in history[:-1]
            if item["volume"] is not None and item["volume"] > 0
        ]
        average_volume = fmean(volumes) if volumes else None
        volume = current["volume"]
        high, low = current["high"], current["low"]
        snapshot = MarketSnapshot(
            symbol=symbol,
            price=current["close"],
            previous_price=previous["close"],
            volume=volume,
            average_volume=average_volume,
            volatility=volatility,
            momentum=momentum,
            open_price=current["open"],
            high_price=high,
            low_price=low,
            close_price=current["close"],
            candle_volume=volume,
            average_candle_volume=average_volume,
            candle_range=(high - low) / current["close"] if high is not None and low is not None and high >= low else None,
            close_position=(
                (current["close"] - low) / (high - low)
                if high is not None and low is not None and high > low and low <= current["close"] <= high
                else None
            ),
            volume_ratio=volume / average_volume if volume is not None and average_volume is not None and average_volume > 0 else None,
            historical_returns=returns,
            historical_return_dates=tuple(item["date"] for item in history[1:]),
            historical_volume_ratios=tuple(
                item["volume"] / fmean(prior["volume"] for prior in history[max(0, j - 20):j] if prior["volume"] is not None and prior["volume"] > 0)
                for j, item in enumerate(history)
                if j > 0 and item["volume"] is not None
                and any(prior["volume"] is not None and prior["volume"] > 0 for prior in history[max(0, j - 20):j])
            ),
        )
        result = pipeline.analyze(snapshot)
        level12 = result.level_12
        for horizon in horizons:
            future = bars[i + 1:i + horizon + 1]
            if len(future) != horizon:
                continue
            adverse_move = max(0.0, (current["close"] - min(item["close"] for item in future)) / current["close"])
            adverse_event = adverse_move >= adverse_move_threshold
            outcomes.append({
                "symbol": symbol,
                "signal_date": current["date"],
                "outcome_date": future[-1]["date"],
                "horizon": horizon,
                "anomaly_score": level12.score,
                "anomaly_confidence": level12.confidence,
                "price_anomaly": level12.price_anomaly,
                "volume_anomaly": level12.volume_anomaly,
                "volatility_anomaly": level12.volatility_anomaly,
                "behavior_anomaly": level12.behavior_anomaly,
                "signal_anomaly": level12.signal_anomaly,
                "data_anomaly": level12.data_anomaly,
                "realized_adverse_move": adverse_move,
                "forward_return": future[-1]["close"] / current["close"] - 1.0,
                "adverse_event": adverse_event,
            })

    summary = {}
    for horizon in horizons:
        group = [item for item in outcomes if item["horizon"] == horizon]
        top_cutoff = sorted(item["anomaly_score"] for item in group)[max(0, int(0.75 * len(group)) - 1)] if group else None
        top_quartile = [item for item in group if top_cutoff is not None and item["anomaly_score"] >= top_cutoff]
        event_rate = sum(item["adverse_event"] for item in group) / len(group) if group else None
        top_event_rate = sum(item["adverse_event"] for item in top_quartile) / len(top_quartile) if top_quartile else None
        summary[f"h{horizon}"] = {
            "count": len(group),
            "adverse_event_rate": event_rate,
            "mean_realized_adverse_move": fmean(item["realized_adverse_move"] for item in group) if group else None,
            "anomaly_adverse_move_correlation": _correlation(
                [item["anomaly_score"] for item in group],
                [item["realized_adverse_move"] for item in group],
            ),
            "threshold_metrics": _binary_metrics(group, anomaly_score_threshold),
            "top_quartile_cutoff": top_cutoff,
            "top_quartile_count": len(top_quartile),
            "top_quartile_adverse_event_rate": top_event_rate,
            "top_quartile_event_rate_lift": (
                top_event_rate / event_rate if top_event_rate is not None and event_rate and event_rate > 0 else None
            ),
        }
    warnings = []
    if len(outcomes) < 30:
        warnings.append("level12_anomaly_outcomes_fewer_than_30")
    return {
        "symbol": symbol,
        "bars": len(bars),
        "outcomes": outcomes,
        "summary": summary,
        "warnings": warnings,
        "methodology": {
            "lookahead": False,
            "snapshot_uses_past_only": True,
            "future_data_used_only_for_outcome": True,
            "horizons": list(horizons),
            "lookback": lookback,
            "adverse_move_threshold": adverse_move_threshold,
            "anomaly_score_threshold": anomaly_score_threshold,
            "top_quartile_selected_per_horizon": True,
            "metrics_are_probabilities": False,
        },
    }


def compare_level_combinations(l4_report: dict, l6_report: dict, l12_report: dict, *, alert_threshold: float = 0.65, round_trip_cost: float = 0.001) -> dict:
    """Compare L4, L4+L6, L4+L12 and L4+L6+L12 on shared historical dates.

    Uses the complete L12 date grid; absent L4 outcomes mean no SELL_PRESSURE
    alert on that date. This is diagnostic classification, not a trade rule.
    """
    if not 0.0 <= alert_threshold <= 1.0:
        raise ValueError("alert_threshold must be between 0 and 1")
    if not isfinite(round_trip_cost) or round_trip_cost < 0:
        raise ValueError("round_trip_cost must be finite and non-negative")
    l4 = {(x["signal_date"], x["horizon"]): x for x in l4_report.get("outcomes", ()) if x.get("signal") == "SELL_PRESSURE"}
    l6 = {(x["signal_date"], x["horizon"]): x for x in l6_report.get("outcomes", ())}
    l12 = {(x["signal_date"], x["horizon"]): x for x in l12_report.get("outcomes", ())}
    rows = []
    for key, anomaly in l12.items():
        risk = l6.get(key)
        pressure = l4.get(key)
        l4_alert = pressure is not None
        l6_alert = risk is not None and risk.get("downside_risk_score", 0.0) >= alert_threshold
        l12_alert = anomaly.get("anomaly_score", 0.0) >= alert_threshold
        rows.append({
            "symbol": anomaly.get("symbol", "UNKNOWN"),
            "signal_date": key[0],
            "outcome_date": anomaly.get("outcome_date", key[0]),
            "horizon": key[1],
            "event": bool(anomaly.get("adverse_event")),
            "forward_return": anomaly.get("forward_return", 0.0),
            "l4_alert": l4_alert,
            "l6_score": risk.get("downside_risk_score") if risk is not None else None,
            "l12_score": anomaly.get("anomaly_score"),
            "l4_l6_alert": l4_alert or l6_alert,
            "l4_l12_alert": l4_alert or l12_alert,
            "l4_l6_l12_alert": l4_alert or l6_alert or l12_alert,
        })
    def metrics(group, name):
        if not group:
            return {"count": 0, "event_rate": None, "alert_rate": None, "precision": None, "recall": None, "false_positive_rate": None, "lift": None}
        alerts = [x for x in group if x[name]]
        events = [x for x in group if x["event"]]
        tp = sum(x["event"] for x in alerts)
        fp = len(alerts) - tp
        event_rate = len(events) / len(group)
        precision = tp / len(alerts) if alerts else None
        recall = tp / len(events) if events else None
        return {
            "count": len(group), "alert_count": len(alerts), "event_count": len(events),
            "event_rate": event_rate, "alert_rate": len(alerts) / len(group),
            "precision": precision, "recall": recall,
            "false_positive_rate": fp / (len(group) - len(events)) if len(group) > len(events) else None,
            "lift": precision / event_rate if precision is not None and event_rate > 0 else None,
        }
    def trading_metrics(group, alert_key, cost):
        # Long-only diagnostic: skip entry on alerts, otherwise exit at horizon close.
        eligible = [x for x in group if alert_key == "__all_dates__" or not x[alert_key]]
        net = [x["forward_return"] - cost for x in eligible]
        baseline = [x["forward_return"] - cost for x in group]
        def compounded(values):
            total = 1.0
            for value in values:
                total *= max(0.0, 1.0 + value)
            return total - 1.0
        def drawdown(values):
            equity = peak = 1.0
            worst = 0.0
            for value in values:
                equity *= max(0.0, 1.0 + value)
                peak = max(peak, equity)
                worst = max(worst, (peak - equity) / peak if peak else 0.0)
            return worst
        return {
            "eligible_trades": len(eligible),
            "coverage": len(eligible) / len(group) if group else None,
            "mean_net_return": fmean(net) if net else None,
            "compounded_net_return": compounded(net) if net else None,
            "win_rate_after_costs": sum(x > 0 for x in net) / len(net) if net else None,
            "max_drawdown_sequential": drawdown(net),
            "round_trip_cost": cost,
            "overlapping_horizons_not_independent": True,
        }
    summary = {}
    for horizon in sorted({x["horizon"] for x in rows}):
        group = [x for x in rows if x["horizon"] == horizon]
        summary[f"h{horizon}"] = {
            "count": len(group),
            "variants": {
                name: {
                    **metrics(group, name),
                    "trading_filter": trading_metrics(group, name, round_trip_cost),
                }
                for name in ("l4_alert", "l4_l6_alert", "l4_l12_alert", "l4_l6_l12_alert")
            },
            "all_dates_reference": trading_metrics(group, "__all_dates__", round_trip_cost),
        }

    # Chronological holdout: all dates before the split are descriptive/training;
    # all dates at/after the split are untouched evaluation data.
    dates = sorted({x["signal_date"] for x in rows})
    split_index = max(1, min(len(dates) - 1, int(len(dates) * 0.70))) if len(dates) >= 2 else len(dates)
    split_date = dates[split_index] if split_index < len(dates) else None
    # Purge training labels that extend into the holdout window. This prevents
    # future return labels from crossing the split boundary.
    train_rows = [
        x for x in rows
        if split_date is not None and x["signal_date"] < split_date
        and x["outcome_date"] < split_date
    ]
    holdout_rows = [x for x in rows if split_date is not None and x["signal_date"] >= split_date]

    threshold_candidates = (0.40, 0.50, 0.60, 0.65, 0.70, 0.80)
    def select_threshold(train_subset, score_key):
        candidates = []
        for threshold in threshold_candidates:
            eligible = [
                x for x in train_subset
                if not x["l4_alert"]
                and (x.get(score_key) is None or x[score_key] < threshold)
            ]
            coverage = len(eligible) / len(train_subset) if train_subset else 0.0
            if not eligible or coverage < 0.50:
                continue
            net_returns = [x["forward_return"] - round_trip_cost for x in eligible]
            candidates.append({
                "threshold": threshold,
                "train_count": len(train_subset),
                "eligible_count": len(eligible),
                "coverage": coverage,
                "mean_net_return": fmean(net_returns),
            })
        if not candidates:
            return {"threshold": alert_threshold, "selection_fallback": True, "candidates": candidates}
        # Optimize training mean net return, then prefer greater coverage and a
        # more conservative (higher) threshold if scores tie.
        chosen = max(candidates, key=lambda x: (x["mean_net_return"], x["coverage"], x["threshold"]))
        return {**chosen, "selection_fallback": False, "candidates": candidates}

    selected_l6 = select_threshold(train_rows, "l6_score")
    selected_l12 = select_threshold(train_rows, "l12_score")

    def selected_metrics(subset, use_l6, use_l12):
        if not subset:
            return {"count": 0, "eligible_count": 0, "coverage": None, "mean_net_return": None, "win_rate_after_costs": None}
        eligible = [
            x for x in subset
            if not x["l4_alert"]
            and (not use_l6 or x.get("l6_score") is None or x["l6_score"] < selected_l6["threshold"])
            and (not use_l12 or x.get("l12_score") is None or x["l12_score"] < selected_l12["threshold"])
        ]
        net = [x["forward_return"] - round_trip_cost for x in eligible]
        compounded = None
        if net:
            equity = 1.0
            for value in net:
                equity *= max(0.0, 1.0 + value)
            compounded = equity - 1.0
        return {
            "count": len(subset), "eligible_count": len(eligible),
            "coverage": len(eligible) / len(subset),
            "mean_net_return": fmean(net) if net else None,
            "compounded_net_return": compounded,
            "win_rate_after_costs": sum(value > 0 for value in net) / len(net) if net else None,
            "round_trip_cost": round_trip_cost,
        }

    selected_holdout = {
        "l4_baseline": selected_metrics(holdout_rows, False, False),
        "l4_l6_train_selected": selected_metrics(holdout_rows, True, False),
        "l4_l12_train_selected": selected_metrics(holdout_rows, False, True),
        "l4_l6_l12_train_selected": selected_metrics(holdout_rows, True, True),
    }

    def summarize_subset(subset):
        output = {}
        for horizon in sorted({x["horizon"] for x in subset}):
            group = [x for x in subset if x["horizon"] == horizon]
            output[f"h{horizon}"] = {
                "count": len(group),
                "event_rate": sum(x["event"] for x in group) / len(group) if group else None,
                "variants": {
                    name: {
                        **metrics(group, name),
                        "trading_filter": trading_metrics(group, name, round_trip_cost),
                    }
                    for name in ("l4_alert", "l4_l6_alert", "l4_l12_alert", "l4_l6_l12_alert")
                },
                "all_dates_reference": trading_metrics(group, "__all_dates__", round_trip_cost),
            }
        return output

    by_symbol = {}
    for symbol in sorted({x.get("symbol", "UNKNOWN") for x in rows}):
        symbol_rows = [x for x in rows if x.get("symbol", "UNKNOWN") == symbol]
        by_symbol[symbol] = summarize_subset(symbol_rows)

    return {
        "outcomes": rows, "summary": summary,
        "chronological_holdout": {
            "split_date": split_date,
            "train_count": len(train_rows),
            "holdout_count": len(holdout_rows),
            "purged_training_outcomes_crossing_split": True,
            "train": summarize_subset(train_rows),
            "holdout": summarize_subset(holdout_rows),
            "threshold_selection": {
                "candidate_thresholds": list(threshold_candidates),
                "objective": "maximize training mean net return after cost, requiring at least 50% coverage",
                "l6": selected_l6,
                "l12": selected_l12,
                "holdout_selected_thresholds": selected_holdout,
            },
        },
        "by_symbol": by_symbol,
        "methodology": {
            "same_dates_for_all_variants": True, "lookahead": False,
            "long_only_risk_filter_simulation": True,
            "alerts_skip_entry_instead_of_shorting": True,
            "round_trip_cost": round_trip_cost,
            "chronological_split": True, "train_fraction": 0.70,
            "holdout_signals_start_on_or_after_split": True,
            "holdout_outcomes_not_used_to_select_alert_threshold": True,
            "training_outcomes_crossing_split_purged": True,
            "threshold_selection_uses_training_only": True,
            "alert_threshold": alert_threshold,
        },
    }
