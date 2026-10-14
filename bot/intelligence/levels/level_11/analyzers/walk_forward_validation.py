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


def evaluate_walk_forward(observations, train_fraction: float = 0.6) -> dict:
    """Chronological holdout evaluation; all learned weights/calibrators use train only.

    This tests whether historical L1-L15 score profiles predict correctness. It does
    not simulate portfolio P&L or change live trading decisions.
    """
    observations = tuple(observations)
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be between 0 and 1")
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
