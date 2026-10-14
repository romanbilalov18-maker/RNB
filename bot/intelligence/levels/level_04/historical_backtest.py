"""Leakage-safe historical evaluation for Level 4 pressure signals.

Each signal uses only the candle that has just closed and earlier candles.
Forward candles are accessed exclusively to score outcomes after the signal.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import fmean, pstdev
from typing import Iterable

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_04.level_04_engine import Level4Engine


@dataclass(frozen=True)
class PressureOutcome:
    symbol: str
    signal_date: str
    signal: str
    pressure_score: float
    horizon: int
    forward_return: float
    net_forward_return: float
    correct_after_costs: bool


def _number(value) -> float | None:
    if value is None:
        return None
    units = getattr(value, "units", None)
    nano = getattr(value, "nano", None)
    try:
        number = float(units) + float(nano or 0) / 1_000_000_000 if units is not None else float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _date(candle, index: int) -> str:
    value = getattr(candle, "time", None) or getattr(candle, "date", None)
    if value is None:
        return str(index)
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _field(candle, name: str) -> float | None:
    return _number(getattr(candle, name, None))


def evaluate_pressure_history(
    candles: Iterable[object],
    *,
    symbol: str = "UNKNOWN",
    horizons: tuple[int, ...] = (1, 3, 5),
    signal_threshold: float = 0.65,
    round_trip_cost: float = 0.001,
    volume_window: int = 20,
) -> dict:
    """Evaluate BUY/SELL pressure with future returns measured after each signal.

    BUY is wrong when its forward return does not exceed estimated round-trip cost.
    SELL is a bearish-pressure indicator (not a short order) and is wrong when
    its forward return is not below negative round-trip cost.
    """
    if not horizons or any(not isinstance(h, int) or h < 1 for h in horizons):
        raise ValueError("horizons must contain positive integers")
    if not 0.0 <= signal_threshold <= 1.0:
        raise ValueError("signal_threshold must be between 0 and 1")
    if not isfinite(round_trip_cost) or round_trip_cost < 0:
        raise ValueError("round_trip_cost must be finite and non-negative")
    if volume_window < 2:
        raise ValueError("volume_window must be at least 2")

    bars = []
    for candle in candles or ():
        open_price, high, low, close, volume = (
            _field(candle, field) for field in ("open", "high", "low", "close", "volume")
        )
        if close is None or close <= 0:
            continue
        bars.append({
            "date": _date(candle, len(bars)),
            "open": open_price, "high": high, "low": low,
            "close": close, "volume": volume if volume is not None and volume >= 0 else None,
        })
    bars.sort(key=lambda item: item["date"])
    if len(bars) < max(horizons) + 2:
        return {
            "symbol": symbol, "bars": len(bars), "signals": 0, "outcomes": [],
            "summary": {}, "warnings": ["historical_candles_insufficient"],
        }

    engine = Level4Engine()
    outcomes: list[PressureOutcome] = []
    warnings: set[str] = set()
    max_horizon = max(horizons)

    # i is the last fully closed candle available at decision time.
    for i in range(1, len(bars) - max_horizon + 1):
        current, previous = bars[i], bars[i - 1]
        if previous["close"] <= 0:
            continue
        price_change = current["close"] / previous["close"] - 1.0
        prior_volumes = [
            bars[j]["volume"] for j in range(max(0, i - volume_window), i)
            if bars[j]["volume"] is not None and bars[j]["volume"] > 0
        ]
        average_volume = fmean(prior_volumes) if prior_volumes else None
        volume_ratio = (
            current["volume"] / average_volume
            if current["volume"] is not None and average_volume is not None and average_volume > 0
            else None
        )
        high, low = current["high"], current["low"]
        close_position = (
            (current["close"] - low) / (high - low)
            if high is not None and low is not None and high > low
            and low <= current["close"] <= high else None
        )
        returns = [
            bars[j]["close"] / bars[j - 1]["close"] - 1.0
            for j in range(1, i + 1) if bars[j - 1]["close"] > 0
        ]
        trailing_returns = returns[-20:]
        volatility = pstdev(trailing_returns) if len(trailing_returns) >= 2 else None
        momentum = (
            current["close"] / bars[max(0, i - 5)]["close"] - 1.0
            if i >= 5 else None
        )
        historical_volume_ratios = []
        for j in range(1, i + 1):
            window = [
                bars[k]["volume"] for k in range(max(0, j - volume_window), j)
                if bars[k]["volume"] is not None and bars[k]["volume"] > 0
            ]
            base = fmean(window) if window else None
            value = bars[j]["volume"]
            if base is not None and base > 0 and value is not None:
                historical_volume_ratios.append(value / base)

        # Keep price returns and volume ratios date-aligned. If volume history
        # is incomplete, leave this feature unavailable instead of shifting pairs.
        aligned_volume_ratios = (
            tuple(historical_volume_ratios)
            if len(historical_volume_ratios) == len(returns) else ()
        )
        snapshot = MarketSnapshot(
            symbol=symbol,
            price=current["close"],
            previous_price=previous["close"],
            volume=current["volume"],
            average_volume=average_volume,
            volatility=volatility,
            momentum=momentum,
            open_price=current["open"],
            high_price=high,
            low_price=low,
            close_price=current["close"],
            candle_volume=current["volume"],
            average_candle_volume=average_volume,
            candle_range=(high - low) / current["close"] if high is not None and low is not None and high >= low else None,
            close_position=close_position,
            volume_ratio=volume_ratio,
            historical_returns=tuple(returns),
            historical_return_dates=tuple(bars[j]["date"] for j in range(1, i + 1)),
            historical_volume_ratios=aligned_volume_ratios,
        )
        result = engine.analyze(snapshot)
        if result.warnings:
            warnings.update(result.warnings)
        buying = result.buying_pressure
        selling = result.selling_pressure
        if buying >= signal_threshold and buying > selling:
            signal, score = "BUY_PRESSURE", buying
        elif selling >= signal_threshold and selling > buying:
            signal, score = "SELL_PRESSURE", selling
        else:
            continue

        # Only now use future bars to grade an already-fixed signal.
        for horizon in horizons:
            future = bars[i + horizon]
            forward_return = future["close"] / current["close"] - 1.0
            net_return = forward_return - round_trip_cost if signal == "BUY_PRESSURE" else -forward_return - round_trip_cost
            correct = net_return > 0.0
            outcomes.append(PressureOutcome(
                symbol=symbol, signal_date=current["date"], signal=signal,
                pressure_score=score, horizon=horizon, forward_return=forward_return,
                net_forward_return=net_return, correct_after_costs=correct,
            ))

    summary = {}
    for horizon in horizons:
        group = [item for item in outcomes if item.horizon == horizon]
        for signal in ("BUY_PRESSURE", "SELL_PRESSURE"):
            subset = [item for item in group if item.signal == signal]
            summary[f"{signal.lower()}_h{horizon}"] = {
                "count": len(subset),
                "win_rate_after_costs": (
                    sum(item.correct_after_costs for item in subset) / len(subset)
                    if subset else None
                ),
                "mean_forward_return": (
                    fmean(item.forward_return for item in subset) if subset else None
                ),
                "mean_net_directional_return": (
                    fmean(item.net_forward_return for item in subset) if subset else None
                ),
                "false_signal_rate": (
                    sum(not item.correct_after_costs for item in subset) / len(subset)
                    if subset else None
                ),
            }
    return {
        "symbol": symbol,
        "bars": len(bars),
        "signals": len({(item.signal_date, item.signal) for item in outcomes}),
        "outcomes": [item.__dict__ for item in outcomes],
        "summary": summary,
        "warnings": sorted(warnings),
        "methodology": {
            "lookahead": False,
            "signal_candle": "closed candle only",
            "volume_baseline": "prior candles only",
            "horizons": list(horizons),
            "signal_threshold": signal_threshold,
            "round_trip_cost": round_trip_cost,
        },
    }
