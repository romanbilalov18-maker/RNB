from __future__ import annotations

from typing import Iterable

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
    if not weights:
        return 0.5
    return sum(weight * scores.get(name, 0.5) for name, weight in weights.items())


def evaluate_walk_forward(observations, train_fraction: float = 0.6) -> dict:
    """Chronological holdout evaluation; all learned weights come from train only.

    This evaluates whether L1-L15 scores predict the historical directional-correctness
    label. It does not simulate portfolio P&L or change live trading decisions.
    """
    observations = tuple(observations)
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be between 0 and 1")
    train_size = int(len(observations) * train_fraction)
    train, test = observations[:train_size], observations[train_size:]
    if train_size < 20 or not test:
        return {
            "status": "insufficient_data",
            "reason": "need at least 20 training observations and one holdout observation",
            "train_count": len(train),
            "test_count": len(test),
            "weights_learned_on_train_only": True,
        }

    level_train = feature_predictive_metrics(train, "level_scores")
    analyzer_train = feature_predictive_metrics(train, "analyzer_scores")
    level_weights = proposed_weights(level_train, len(train))
    analyzer_weights = proposed_weights(analyzer_train, len(train))

    level_baseline = [
        _equal_weight_prediction(item.level_scores) for item in test
    ]
    level_weighted = [
        _weighted_prediction(item.level_scores, level_weights) for item in test
    ]
    analyzer_baseline = [
        _equal_weight_prediction(item.analyzer_scores) for item in test
    ]
    analyzer_weighted = [
        _weighted_prediction(item.analyzer_scores, analyzer_weights) for item in test
    ]
    return {
        "status": "evaluated",
        "train_count": len(train),
        "test_count": len(test),
        "weights_learned_on_train_only": True,
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
            "Compare holdout Brier score (lower is better) and AUC (higher is better). "
            "Do not deploy weights unless performance improves on multiple time-ordered windows."
        ),
    }
