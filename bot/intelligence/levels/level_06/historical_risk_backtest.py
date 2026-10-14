"""Leakage-safe historical evaluation of Level 6 risk estimates."""
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
    left_sum = sum((x - left_mean) ** 2 for x in left)
    right_sum = sum((y - right_mean) ** 2 for y in right)
    denominator = sqrt(left_sum * right_sum)
    return numerator / denominator if denominator > 0 else None


def evaluate_level6_risk_history(
    candles: Iterable[object],
    *,
    symbol: str = "UNKNOWN",
    horizons: tuple[int, ...] = (1, 3, 5),
    lookback: int = 20,
) -> dict:
    """Compare Level 6 risk scores with subsequent realized drawdown and volatility.

    Each snapshot is built solely from candles up to its decision date. Future
    candles are used only to calculate the realized labels for each horizon.
    This is a diagnostic backtest, not a probability calibration or trade rule.
    """
    if not horizons or any(not isinstance(h, int) or h < 1 for h in horizons):
        raise ValueError("horizons must contain positive integers")
    if lookback < 5:
        raise ValueError("lookback must be at least 5")

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
            "warnings": ["level6_risk_history_insufficient"],
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
        volumes = [item["volume"] for item in history[:-1] if item["volume"] is not None and item["volume"] > 0]
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
        )
        result = pipeline.analyze(snapshot).level_06
        for horizon in horizons:
            future = bars[i + 1:i + horizon + 1]
            if len(future) != horizon:
                continue
            forward_returns = []
            previous_close = current["close"]
            for future_bar in future:
                forward_returns.append(future_bar["close"] / previous_close - 1.0)
                previous_close = future_bar["close"]
            running_peak = current["close"]
            max_drawdown = 0.0
            for future_bar in future:
                running_peak = max(running_peak, future_bar["close"])
                if running_peak > 0:
                    max_drawdown = max(max_drawdown, (running_peak - future_bar["close"]) / running_peak)
            realized_volatility = pstdev(forward_returns) if len(forward_returns) > 1 else abs(forward_returns[0])
            outcomes.append({
                "symbol": symbol,
                "signal_date": current["date"],
                "outcome_date": future[-1]["date"],
                "horizon": horizon,
                "level6_score": result.score,
                "level6_confidence": result.confidence,
                "downside_risk_score": result.downside_risk,
                "volatility_risk_score": result.volatility_risk,
                "realized_max_drawdown": max_drawdown,
                "realized_volatility": realized_volatility,
            })

    summary = {}
    for horizon in horizons:
        group = [item for item in outcomes if item["horizon"] == horizon]
        summary[f"h{horizon}"] = {
            "count": len(group),
            "mean_downside_risk_score": fmean(item["downside_risk_score"] for item in group) if group else None,
            "mean_realized_max_drawdown": fmean(item["realized_max_drawdown"] for item in group) if group else None,
            "downside_score_drawdown_correlation": _correlation(
                [item["downside_risk_score"] for item in group],
                [item["realized_max_drawdown"] for item in group],
            ),
            "mean_volatility_risk_score": fmean(item["volatility_risk_score"] for item in group) if group else None,
            "mean_realized_volatility": fmean(item["realized_volatility"] for item in group) if group else None,
            "volatility_score_realized_volatility_correlation": _correlation(
                [item["volatility_risk_score"] for item in group],
                [item["realized_volatility"] for item in group],
            ),
        }
    warnings = []
    if len(outcomes) < 30:
        warnings.append("level6_risk_outcomes_fewer_than_30")
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
            "metrics_are_probabilities": False,
        },
    }
