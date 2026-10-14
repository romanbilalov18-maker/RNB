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
        future = bars[i + 1:i + horizon + 1] if False else None
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
