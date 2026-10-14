from __future__ import annotations

from bot.intelligence.levels.level_11.analyzers.predictive_skill import (
    feature_predictive_metrics,
    proposed_weights,
)


def _auc(labels: list[bool], scores: list[float]) -> float | None:
    positives = sum(labels)
    negatives = len(labels) - positives
    if not positives or not negatives:
        return None
    wins = 0.0
    for i, label in enumerate(labels):
        if label:
            wins += sum(
                1.0 if scores[i] > scores[j] else 0.5 if scores[i] == scores[j] else 0.0
                for j, other in enumerate(labels)
                if not other
            )
    return wins / (positives * negatives)


def _metrics(observations, predictions: list[float]) -> dict:
    labels = [bool(item.correct) for item in observations]
    if not labels:
        return {"brier_score": None, "auc": None, "accuracy_at_0_5": None}
    predictions = [max(0.0, min(1.0, float(value))) for value in predictions]
    return {
        "brier_score": sum((p - float(label)) ** 2 for p, label in zip(predictions, labels)) / len(labels),
        "auc": _auc(labels, predictions),
        "accuracy_at_0_5": sum((p >= 0.5) == label for p, label in zip(predictions, labels)) / len(labels),
    }


def _equal_weight_prediction(scores: dict[str, float]) -> float:
    return sum(scores.values()) / len(scores) if scores else 0.5


def _weighted_prediction(scores: dict[str, float], weights: dict[str, float]) -> float:
    # Renormalize over features actually present in this observation. Treating
    # missing features as a neutral 0.5 without renormalization silently shrinks
    # the prediction toward zero and unfairly penalizes rows with sparse history.
    available = [
        (weight, float(scores[name]))
        for name, weight in weights.items()
        if name in scores
    ]
    total_weight = sum(weight for weight, _ in available)
    if total_weight <= 1e-12:
        return 0.5
    return sum(weight * score for weight, score in available) / total_weight


def _fit_linear_calibrator(raw_scores: list[float], labels: list[bool]) -> tuple[float, float]:
    """Fit a simple train-only linear calibration mapping to correctness probability."""
    if not raw_scores or len(raw_scores) != len(labels):
        return 0.0, 0.5
    x_mean = sum(raw_scores) / len(raw_scores)
    y_mean = sum(float(label) for label in labels) / len(labels)
    variance = sum((x - x_mean) ** 2 for x in raw_scores)
    covariance = sum((x - x_mean) * (float(y) - y_mean) for x, y in zip(raw_scores, labels))
    slope = covariance / variance if variance > 1e-12 else 0.0
    intercept = y_mean - slope * x_mean
    return slope, intercept


def _calibrate(raw_scores: list[float], parameters: tuple[float, float]) -> list[float]:
    slope, intercept = parameters
    return [max(0.0, min(1.0, slope * score + intercept)) for score in raw_scores]


def _prepare_chronological_observations(observations):
    observations = tuple(observations)
    timestamps = [getattr(item, "decision_time", None) for item in observations]
    has_timestamps = [bool(value) for value in timestamps]
    if any(has_timestamps) and not all(has_timestamps):
        return observations, False, "decision timestamps are incomplete"
    if all(has_timestamps) and timestamps:
        return tuple(sorted(observations, key=lambda item: item.decision_time)), True, None
    # Legacy/synthetic callers may not provide timestamps. Preserve their
    # explicit order, but report that chronology could not be independently verified.
    return observations, False, None


def evaluate_walk_forward(observations, train_fraction: float = 0.6) -> dict:
    """Chronological holdout evaluation; all learned weights/calibrators use train only.

    This tests whether historical L1-L15 score profiles predict correctness. It does
    not simulate portfolio P&L or change live trading decisions.
    """
    observations, chronology_verified, chronology_error = _prepare_chronological_observations(observations)
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be between 0 and 1")
    if chronology_error:
        return {
            "status": "insufficient_data",
            "reason": chronology_error,
            "train_count": 0,
            "raw_train_count": 0,
            "purged_train_count": 0,
            "test_count": len(observations),
            "chronology_verified": False,
            "weights_learned_on_train_only": True,
            "calibrators_learned_on_train_only": True,
        }
    train_size = int(len(observations) * train_fraction)
    raw_train, test = observations[:train_size], observations[train_size:]
    # Purge training labels whose forward outcome reaches the holdout period.
    # The features were recorded at decision time, but a 3-session label may
    # mature after a later holdout decision; that label is not yet knowable at
    # the holdout boundary and must not influence fitted weights/calibrators.
    boundary = next((item.decision_time for item in test if item.decision_time), None)
    train = tuple(
        item for item in raw_train
        if not (
            boundary and item.outcome_target_date
            and item.outcome_target_date >= boundary[:10]
        )
    )
    purged_train_count = len(raw_train) - len(train)
    if len(train) < 20 or not test:
        return {
            "status": "insufficient_data",
            "reason": "need at least 20 training observations after temporal purging and one holdout observation",
            "train_count": len(train),
            "raw_train_count": len(raw_train),
            "purged_train_count": purged_train_count,
            "test_count": len(test),
            "purging_applied": boundary is not None,
        "chronology_verified": chronology_verified,
            "chronology_verified": chronology_verified,
            "weights_learned_on_train_only": True,
            "calibrators_learned_on_train_only": True,
        }

    level_train = feature_predictive_metrics(train, "level_scores")
    analyzer_train = feature_predictive_metrics(train, "analyzer_scores")
    level_weights = proposed_weights(level_train, len(train))
    analyzer_weights = proposed_weights(analyzer_train, len(train))

    train_labels = [bool(item.correct) for item in train]
    train_level_baseline = [_equal_weight_prediction(item.level_scores) for item in train]
    train_level_weighted = [_weighted_prediction(item.level_scores, level_weights) for item in train]
    train_analyzer_baseline = [_equal_weight_prediction(item.analyzer_scores) for item in train]
    train_analyzer_weighted = [_weighted_prediction(item.analyzer_scores, analyzer_weights) for item in train]

    calibrators = {
        "level_baseline": _fit_linear_calibrator(train_level_baseline, train_labels),
        "level_weighted": _fit_linear_calibrator(train_level_weighted, train_labels),
        "analyzer_baseline": _fit_linear_calibrator(train_analyzer_baseline, train_labels),
        "analyzer_weighted": _fit_linear_calibrator(train_analyzer_weighted, train_labels),
    }

    level_baseline = _calibrate(
        [_equal_weight_prediction(item.level_scores) for item in test],
        calibrators["level_baseline"],
    )
    level_weighted = _calibrate(
        [_weighted_prediction(item.level_scores, level_weights) for item in test],
        calibrators["level_weighted"],
    )
    analyzer_baseline = _calibrate(
        [_equal_weight_prediction(item.analyzer_scores) for item in test],
        calibrators["analyzer_baseline"],
    )
    analyzer_weighted = _calibrate(
        [_weighted_prediction(item.analyzer_scores, analyzer_weights) for item in test],
        calibrators["analyzer_weighted"],
    )
    return {
        "status": "evaluated",
        "train_count": len(train),
        "raw_train_count": len(raw_train),
        "purged_train_count": purged_train_count,
        "test_count": len(test),
        "purging_applied": boundary is not None,
        "weights_learned_on_train_only": True,
        "calibrators_learned_on_train_only": True,
        "level_weights": level_weights,
        "analyzer_weights": analyzer_weights,
        "levels": {
            "equal_weight_baseline": _metrics(test, level_baseline),
            "proposed_weighted": _metrics(test, level_weighted),
        },
        "analyzers": {
            "equal_weight_baseline": _metrics(test, analyzer_baseline),
            "proposed_weighted": _metrics(test, analyzer_weighted),
        },
        "interpretation": (
            "Scores are calibrated using training data only. Compare holdout Brier score "
            "(lower is better) and AUC (higher is better). Do not deploy weights unless "
            "multiple time-ordered windows and transaction-cost-aware backtests confirm improvement."
        ),
    }

def evaluate_multiple_windows(observations, window_count: int = 3, min_test_size: int = 10) -> dict:
    """Evaluate expanding, chronological holdout windows with disjoint test slices."""
    observations, chronology_verified, chronology_error = _prepare_chronological_observations(observations)
    if chronology_error:
        return {
            "status": "insufficient_data",
            "reason": chronology_error,
            "requested_windows": window_count,
            "evaluated_windows": 0,
            "windows": [],
            "chronology_verified": False,
            "deployment_allowed": False,
        }
    if window_count < 2:
        raise ValueError("window_count must be at least 2")
    if min_test_size < 1:
        raise ValueError("min_test_size must be positive")
    test_size = max(min_test_size, len(observations) // (window_count + 2))
    windows = []
    for index in range(window_count):
        end = len(observations) - (window_count - index - 1) * test_size
        start = end - test_size
        if start <= 0:
            continue
        fraction = start / end
        result = evaluate_walk_forward(observations[:end], train_fraction=fraction)
        if result.get("status") == "evaluated" and result.get("test_count") == test_size:
            result = {**result, "window": index + 1,
                      "train_end_index": result["raw_train_count"],
                      "test_start_index": start, "test_end_index": end}
            windows.append(result)

    if len(windows) < 2:
        return {
            "status": "insufficient_data",
            "reason": "at least two valid chronological holdout windows are required",
            "requested_windows": window_count,
            "evaluated_windows": len(windows),
            "windows": windows,
            "deployment_allowed": False,
            "chronology_verified": chronology_verified,
        }

    def mean_metric(section: str, model: str, metric: str):
        values = [
            item[section][model][metric]
            for item in windows
            if item[section][model].get(metric) is not None
        ]
        return sum(values) / len(values) if values else None

    summary = {}
    for section in ("levels", "analyzers"):
        summary[section] = {}
        for model in ("equal_weight_baseline", "proposed_weighted"):
            summary[section][model] = {
                metric: mean_metric(section, model, metric)
                for metric in ("brier_score", "auc", "accuracy_at_0_5")
            }
        baseline = summary[section]["equal_weight_baseline"]
        proposed = summary[section]["proposed_weighted"]
        base_brier, proposed_brier = baseline["brier_score"], proposed["brier_score"]
        base_auc, proposed_auc = baseline["auc"], proposed["auc"]
        summary[section]["delta"] = {
            "brier_score": (
                proposed_brier - base_brier
                if proposed_brier is not None and base_brier is not None else None
            ),
            "auc": (
                proposed_auc - base_auc
                if proposed_auc is not None and base_auc is not None else None
            ),
        }

    return {
        "status": "evaluated",
        "requested_windows": window_count,
        "evaluated_windows": len(windows),
        "test_size_per_window": test_size,
        "windows": windows,
        "summary": summary,
        "deployment_allowed": False,
        "chronology_verified": chronology_verified,
        "interpretation": (
            "Window metrics are unweighted means across disjoint chronological holdouts. "
            "Negative Brier delta and positive AUC delta favor the proposed model. "
            "This diagnostic does not authorize deployment."
        ),
    }
