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
    outcome_date: str
    market_regime: str


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
    market_regime_by_date: dict[str, str] | None = None,
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
    for i in range(1, len(bars) - max_horizon):
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
        market_regime = (market_regime_by_date or {}).get(current["date"], "UNCLASSIFIED")
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
                outcome_date=future["date"], market_regime=market_regime,
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


def build_market_regime_by_date(
    candle_history: dict[str, Iterable[object]],
    *,
    lookback: int = 20,
    bull_threshold: float = 0.03,
    bear_threshold: float = -0.03,
) -> dict[str, str]:
    """Create a date-aligned, equal-weight scanned-universe regime proxy.

    Each date's return is the mean return of instruments with adjacent closes
    on that date. A regime uses only returns available on or before its signal
    date, so future candles cannot alter a historical regime label.
    """
    if lookback < 2:
        raise ValueError("lookback must be at least 2")
    if not isfinite(bull_threshold) or not isfinite(bear_threshold) or bear_threshold >= bull_threshold:
        raise ValueError("regime thresholds must be finite and bear_threshold < bull_threshold")

    returns_by_date: dict[str, list[float]] = {}
    for candles in (candle_history or {}).values():
        points = []
        for index, candle in enumerate(candles or ()):
            close = _field(candle, "close")
            day = _date(candle, index)
            if close is not None and close > 0:
                points.append((day, close))
        points.sort()
        for (previous_day, previous), (day, current) in zip(points, points[1:]):
            if previous > 0 and current > 0 and day != previous_day:
                returns_by_date.setdefault(day, []).append(current / previous - 1.0)

    market_returns = {
        day: fmean(values) for day, values in returns_by_date.items() if values
    }
    ordered_dates = sorted(market_returns)
    regimes: dict[str, str] = {}
    for index, day in enumerate(ordered_dates):
        trailing = ordered_dates[max(0, index - lookback + 1):index + 1]
        cumulative = 1.0
        for trailing_day in trailing:
            cumulative *= 1.0 + market_returns[trailing_day]
        cumulative -= 1.0
        if cumulative >= bull_threshold:
            regime = "BULL"
        elif cumulative <= bear_threshold:
            regime = "BEAR"
        else:
            regime = "SIDEWAYS"
        regimes[day] = regime
    return regimes


def evaluate_pressure_walk_forward(
    candles: Iterable[object],
    *,
    symbol: str = "UNKNOWN",
    horizons: tuple[int, ...] = (1, 3, 5),
    signal_threshold: float = 0.65,
    round_trip_cost: float = 0.001,
    train_fraction: float = 0.70,
    market_regime_by_date: dict[str, str] | None = None,
    threshold_candidates: tuple[float, ...] = (0.55, 0.65, 0.75),
    min_train_outcomes: int = 20,
) -> dict:
    """Select a pressure threshold on training data and evaluate it on later data.

    Training outcomes are eligible only if their full forward horizon ends
    strictly before the split. Holdout signals begin on/after the split.
    """
    if not horizons or any(not isinstance(h, int) or h < 1 for h in horizons):
        raise ValueError("horizons must contain positive integers")
    if not isfinite(signal_threshold) or not 0.0 <= signal_threshold <= 1.0:
        raise ValueError("signal_threshold must be between 0 and 1")
    if not isfinite(round_trip_cost) or round_trip_cost < 0:
        raise ValueError("round_trip_cost must be finite and non-negative")
    if not isfinite(train_fraction) or not 0.5 <= train_fraction <= 0.85:
        raise ValueError("train_fraction must be between 0.5 and 0.85")
    if not threshold_candidates or any(
        not isfinite(value) or not 0.0 <= value <= 1.0
        for value in threshold_candidates
    ):
        raise ValueError("threshold_candidates must contain values between 0 and 1")
    if min_train_outcomes < 1:
        raise ValueError("min_train_outcomes must be positive")

    bars = []
    for index, candle in enumerate(candles or ()):
        close = _field(candle, "close")
        if close is not None and close > 0:
            bars.append((_date(candle, index), close))
    bars.sort()
    if len(bars) < max(horizons) + 12:
        return {
            "symbol": symbol,
            "bars": len(bars),
            "split_date": None,
            "selected_threshold": signal_threshold,
            "baseline_threshold": 0.65 if 0.65 in threshold_candidates else signal_threshold,
            "threshold_selection": {
                "selection_source": "training outcomes only",
                "minimum_training_outcomes": min_train_outcomes,
                "scores_mean_net_directional_return": {},
                "selected_threshold_score": None,
                "eligible_threshold_count": 0,
                "fallback_used": True,
            },
            "train": {"signals": 0, "outcomes": [], "summary": {}},
            "holdout": {"signals": 0, "outcomes": [], "summary": {}},
            "baseline_holdout": {"signals": 0, "outcomes": [], "summary": {}},
            "warnings": ["walk_forward_history_insufficient"],
            "methodology": {
                "chronological_split": True,
                "lookahead": False,
                "threshold_selection_uses_training_only": True,
            },
        }

    split_index = min(len(bars) - 1, max(1, int(len(bars) * train_fraction)))
    split_date = bars[split_index][0]
    candidates = tuple(sorted(set(threshold_candidates)))
    full_by_threshold = {
        threshold: evaluate_pressure_history(
            candles,
            symbol=symbol,
            horizons=horizons,
            signal_threshold=threshold,
            round_trip_cost=round_trip_cost,
            market_regime_by_date=market_regime_by_date,
        )
        for threshold in candidates
    }

    # Tune only on outcomes whose full forward horizon is before the split.
    threshold_scores = {}
    train_by_threshold = {}
    for threshold, report in full_by_threshold.items():
        train_items = [
            item for item in report["outcomes"] if item["outcome_date"] < split_date
        ]
        train_by_threshold[threshold] = train_items
        threshold_scores[threshold] = (
            fmean(item["net_forward_return"] for item in train_items)
            if len(train_items) >= min_train_outcomes else None
        )

    eligible = [threshold for threshold, score in threshold_scores.items() if score is not None]
    baseline_threshold = 0.65 if 0.65 in full_by_threshold else min(
        candidates, key=lambda value: abs(value - 0.65)
    )
    selected_threshold = (
        max(eligible, key=lambda threshold: (
            threshold_scores[threshold], threshold == baseline_threshold
        ))
        if eligible else baseline_threshold
    )

    selected_report = full_by_threshold[selected_threshold]
    train_outcomes = train_by_threshold[selected_threshold]
    holdout_outcomes = [
        item for item in selected_report["outcomes"] if item["signal_date"] >= split_date
    ]
    baseline_report = full_by_threshold[baseline_threshold]
    baseline_holdout_outcomes = [
        item for item in baseline_report["outcomes"] if item["signal_date"] >= split_date
    ]

    def summarize(items: list[dict]) -> dict:
        summary = {}
        regimes = sorted({item["market_regime"] for item in items}) or ["UNCLASSIFIED"]
        for horizon in horizons:
            for signal in ("BUY_PRESSURE", "SELL_PRESSURE"):
                for regime in regimes:
                    subset = [
                        item for item in items
                        if item["horizon"] == horizon
                        and item["signal"] == signal
                        and item["market_regime"] == regime
                    ]
                    summary[f"{signal.lower()}_h{horizon}_{regime.lower()}"] = {
                        "count": len(subset),
                        "win_rate_after_costs": (
                            sum(item["correct_after_costs"] for item in subset) / len(subset)
                            if subset else None
                        ),
                        "mean_forward_return": (
                            fmean(item["forward_return"] for item in subset) if subset else None
                        ),
                        "mean_net_directional_return": (
                            fmean(item["net_forward_return"] for item in subset) if subset else None
                        ),
                        "false_signal_rate": (
                            sum(not item["correct_after_costs"] for item in subset) / len(subset)
                            if subset else None
                        ),
                    }
        return summary

    warnings = list(dict.fromkeys(
        warning
        for report in full_by_threshold.values()
        for warning in report["warnings"]
    ))
    if len(holdout_outcomes) < 30:
        warnings.append("holdout_has_fewer_than_30_outcomes")

    return {
        "symbol": symbol,
        "bars": len(bars),
        "split_date": split_date,
        "selected_threshold": selected_threshold,
        "baseline_threshold": baseline_threshold,
        "threshold_selection": {
            "selection_source": "training outcomes only",
            "minimum_training_outcomes": min_train_outcomes,
            "scores_mean_net_directional_return": threshold_scores,
            "selected_threshold_score": threshold_scores[selected_threshold],
            "eligible_threshold_count": len(eligible),
            "fallback_used": not bool(eligible),
        },
        "train": {
            "signals": len({(item["signal_date"], item["signal"]) for item in train_outcomes}),
            "outcomes": train_outcomes,
            "summary": summarize(train_outcomes),
        },
        "holdout": {
            "signals": len({(item["signal_date"], item["signal"]) for item in holdout_outcomes}),
            "outcomes": holdout_outcomes,
            "summary": summarize(holdout_outcomes),
        },
        "baseline_holdout": {
            "signals": len({(item["signal_date"], item["signal"]) for item in baseline_holdout_outcomes}),
            "outcomes": baseline_holdout_outcomes,
            "summary": summarize(baseline_holdout_outcomes),
        },
        "warnings": warnings,
        "methodology": {
            "chronological_split": True,
            "train_fraction": train_fraction,
            "train_outcomes_end_before_split": True,
            "holdout_signals_start_on_or_after_split": True,
            "lookahead": False,
            "regime_source": (
                "equal_weight_scanned_universe_proxy"
                if market_regime_by_date else "unclassified_no_market_proxy"
            ),
            "initial_signal_threshold": signal_threshold,
            "threshold_candidates": list(candidates),
            "threshold_selection_uses_training_only": True,
            "round_trip_cost": round_trip_cost,
        },
    }


def evaluate_pressure_rolling_walk_forward(
    candles: Iterable[object],
    *,
    symbol: str = "UNKNOWN",
    horizons: tuple[int, ...] = (1, 3, 5),
    round_trip_cost: float = 0.001,
    train_fraction: float = 0.50,
    holdout_fraction: float = 0.20,
    step_fraction: float = 0.15,
    market_regime_by_date: dict[str, str] | None = None,
    threshold_candidates: tuple[float, ...] = (0.55, 0.65, 0.75),
    min_train_outcomes: int = 20,
) -> dict:
    """Run sequential expanding-window evaluations without reusing holdout labels.

    Each window selects a threshold from training outcomes ending before the
    window's holdout starts. Holdout outcomes must also finish before the next
    window boundary. Window metrics are reported separately and in aggregate.
    """
    if not 0.3 <= train_fraction <= 0.8:
        raise ValueError("train_fraction must be between 0.3 and 0.8")
    if not 0.1 <= holdout_fraction <= 0.4:
        raise ValueError("holdout_fraction must be between 0.1 and 0.4")
    if not 0.05 <= step_fraction <= holdout_fraction:
        raise ValueError("step_fraction must be between 0.05 and holdout_fraction")
    if not horizons or any(not isinstance(h, int) or h < 1 for h in horizons):
        raise ValueError("horizons must contain positive integers")
    if not threshold_candidates or any(
        not isfinite(value) or not 0.0 <= value <= 1.0
        for value in threshold_candidates
    ):
        raise ValueError("threshold_candidates must contain values between 0 and 1")
    if min_train_outcomes < 1:
        raise ValueError("min_train_outcomes must be positive")
    if not isfinite(round_trip_cost) or round_trip_cost < 0:
        raise ValueError("round_trip_cost must be finite and non-negative")

    bars = []
    for index, candle in enumerate(candles or ()):
        close = _field(candle, "close")
        if close is not None and close > 0:
            bars.append((_date(candle, index), close))
    bars.sort()
    n = len(bars)
    initial_train_end = int(n * train_fraction)
    holdout_size = max(max(horizons) + 1, int(n * holdout_fraction))
    step_size = max(1, int(n * step_fraction))
    if initial_train_end < max(horizons) + 12 or initial_train_end + max(horizons) + 1 >= n:
        return {
            "symbol": symbol,
            "bars": n,
            "windows": [],
            "aggregate": {"count": 0, "win_rate_after_costs": None, "mean_net_directional_return": None},
            "warnings": ["rolling_walk_forward_history_insufficient"],
            "methodology": {"lookahead": False, "threshold_selection_uses_training_only": True},
        }

    candidates = tuple(sorted(set(threshold_candidates)))
    windows = []
    train_end = initial_train_end
    while train_end < n - max(horizons):
        holdout_end = min(n, train_end + holdout_size)
        if holdout_end - train_end <= max(horizons):
            break
        split_date = bars[train_end][0]
        holdout_end_date = bars[holdout_end - 1][0]
        reports = {
            threshold: evaluate_pressure_history(
                candles,
                symbol=symbol,
                horizons=horizons,
                signal_threshold=threshold,
                round_trip_cost=round_trip_cost,
                market_regime_by_date=market_regime_by_date,
            )
            for threshold in candidates
        }
        train_by_threshold = {
            threshold: [
                item for item in report["outcomes"]
                if item["outcome_date"] < split_date
            ]
            for threshold, report in reports.items()
        }
        scores = {
            threshold: (
                fmean(item["net_forward_return"] for item in outcomes)
                if len(outcomes) >= min_train_outcomes else None
            )
            for threshold, outcomes in train_by_threshold.items()
        }
        eligible = [threshold for threshold, score in scores.items() if score is not None]
        baseline = 0.65 if 0.65 in reports else min(candidates, key=lambda value: abs(value - 0.65))
        selected = (
            max(eligible, key=lambda threshold: (scores[threshold], threshold == baseline))
            if eligible else baseline
        )
        selected_outcomes = [
            item for item in reports[selected]["outcomes"]
            if item["signal_date"] >= split_date
            and item["signal_date"] < holdout_end_date
            and item["outcome_date"] <= holdout_end_date
        ]
        baseline_outcomes = [
            item for item in reports[baseline]["outcomes"]
            if item["signal_date"] >= split_date
            and item["signal_date"] < holdout_end_date
            and item["outcome_date"] <= holdout_end_date
        ]
        windows.append({
            "train_start": bars[0][0],
            "train_end": bars[train_end - 1][0],
            "holdout_start": split_date,
            "holdout_end": holdout_end_date,
            "selected_threshold": selected,
            "baseline_threshold": baseline,
            "threshold_scores": scores,
            "fallback_used": not bool(eligible),
            "selected_outcomes": selected_outcomes,
            "baseline_outcomes": baseline_outcomes,
            "selected_metrics": _pressure_metrics(selected_outcomes),
            "baseline_metrics": _pressure_metrics(baseline_outcomes),
        })
        if holdout_end == n:
            break
        train_end += step_size

    selected_all = [item for window in windows for item in window["selected_outcomes"]]
    baseline_all = [item for window in windows for item in window["baseline_outcomes"]]
    return {
        "symbol": symbol,
        "bars": n,
        "windows": windows,
        "aggregate": _pressure_metrics(selected_all),
        "baseline_aggregate": _pressure_metrics(baseline_all),
        "warnings": (
            ["rolling_holdout_has_fewer_than_30_outcomes"]
            if len(selected_all) < 30 else []
        ),
        "methodology": {
            "lookahead": False,
            "windowing": "expanding training window with sequential non-overlapping holdout blocks",
            "train_fraction_initial": train_fraction,
            "holdout_fraction": holdout_fraction,
            "step_fraction": step_fraction,
            "threshold_selection_uses_training_only": True,
            "holdout_outcomes_end_within_each_window": True,
            "threshold_candidates": list(candidates),
            "round_trip_cost": round_trip_cost,
        },
    }


def _pressure_metrics(items: list[dict]) -> dict:
    return {
        "count": len(items),
        "win_rate_after_costs": (
            sum(item["correct_after_costs"] for item in items) / len(items)
            if items else None
        ),
        "mean_net_directional_return": (
            fmean(item["net_forward_return"] for item in items) if items else None
        ),
        "false_signal_rate": (
            sum(not item["correct_after_costs"] for item in items) / len(items)
            if items else None
        ),
    }
