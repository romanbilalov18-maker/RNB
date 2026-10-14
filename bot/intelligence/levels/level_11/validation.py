"""Chronological out-of-sample evaluation for L11 shadow weight proposals.

This module is diagnostic only: it never changes DecisionEngine or trading weights.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from bot.intelligence.levels.level_11.analyzers.predictive_skill import (
    feature_predictive_metrics,
    proposed_weights,
)
from bot.intelligence.levels.level_11.models.learning_observation import LearningObservation


@dataclass(frozen=True)
class ValidationMetrics:
    sample_count: int
    brier_score: float | None
    accuracy_at_half: float | None
    auc: float | None


def _auc(labels: list[int], scores: list[float]) -> float | None:
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return None
    ordered = sorted(zip(scores, labels), key=lambda item: item[0])
    rank_sum = 0.0
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        average_rank = ((index + 1) + end) / 2.0
        rank_sum += average_rank * sum(label for _, label in ordered[index:end])
        index = end
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def _metrics(labels: list[int], predictions: list[float]) -> ValidationMetrics:
    if not labels:
        return ValidationMetrics(0, None, None, None)
    brier = sum((prediction - label) ** 2 for label, prediction in zip(labels, predictions)) / len(labels)
    accuracy = sum((prediction >= 0.5) == bool(label) for label, prediction in zip(labels, predictions)) / len(labels)
    return ValidationMetrics(len(labels), brier, accuracy, _auc(labels, predictions))


def _weighted_score(scores: dict[str, float], weights: dict[str, float]) -> float | None:
    available = [(weights[name], value) for name, value in scores.items() if name in weights]
    total = sum(weight for weight, _ in available)
    if total <= 1e-12:
        return None
    return sum(weight * value for weight, value in available) / total


def evaluate_feature_group(
    observations: Iterable[LearningObservation],
    attribute: str,
    *,
    train_fraction: float = 0.7,
    min_train_samples: int = 20,
    min_test_samples: int = 5,
) -> dict:
    """Fit proposals on the earlier observations and compare on later observations."""
    rows = tuple(observations)
    if attribute not in {"level_scores", "analyzer_scores"}:
        raise ValueError("attribute must be 'level_scores' or 'analyzer_scores'")
    if not 0.5 <= train_fraction < 1.0:
        raise ValueError("train_fraction must be in [0.5, 1.0)")
    split = int(len(rows) * train_fraction)
    train, test = rows[:split], rows[split:]
    report = {
        "feature_group": attribute,
        "total_samples": len(rows),
        "train_samples": len(train),
        "test_samples": len(test),
        "train_fraction": train_fraction,
        "baseline": asdict(ValidationMetrics(0, None, None, None)),
        "adaptive": asdict(ValidationMetrics(0, None, None, None)),
        "proposed_weights": {},
        "status": "insufficient_history",
        "adaptive_minus_baseline_auc": None,
        "adaptive_minus_baseline_brier": None,
    }
    if len(train) < min_train_samples or len(test) < min_test_samples:
        return report

    train_metrics = feature_predictive_metrics(train, attribute)
    weights = proposed_weights(train_metrics, len(train))
    if not weights:
        report["status"] = "no_trainable_proposal"
        return report

    feature_names = sorted({
        name for row in train for name in getattr(row, attribute, {})
        if name in weights
    })
    if not feature_names:
        report["status"] = "no_common_features"
        return report
    baseline_weights = {name: 1.0 for name in feature_names}
    labels: list[int] = []
    baseline_predictions: list[float] = []
    adaptive_predictions: list[float] = []
    for row in test:
        scores = getattr(row, attribute, {})
        baseline = _weighted_score(scores, baseline_weights)
        adaptive = _weighted_score(scores, weights)
        if baseline is None or adaptive is None:
            continue
        labels.append(int(bool(row.correct)))
        baseline_predictions.append(max(0.0, min(1.0, baseline)))
        adaptive_predictions.append(max(0.0, min(1.0, adaptive)))

    if len(labels) < min_test_samples:
        report["status"] = "insufficient_test_feature_coverage"
        return report
    baseline_result = _metrics(labels, baseline_predictions)
    adaptive_result = _metrics(labels, adaptive_predictions)
    report.update({
        "baseline": asdict(baseline_result),
        "adaptive": asdict(adaptive_result),
        "proposed_weights": weights,
        "status": "evaluated",
        "adaptive_minus_baseline_auc": (
            adaptive_result.auc - baseline_result.auc
            if adaptive_result.auc is not None and baseline_result.auc is not None else None
        ),
        "adaptive_minus_baseline_brier": (
            adaptive_result.brier_score - baseline_result.brier_score
            if adaptive_result.brier_score is not None and baseline_result.brier_score is not None else None
        ),
        "interpretation": (
            "adaptive_better" if (
                adaptive_result.auc is not None and baseline_result.auc is not None
                and adaptive_result.auc > baseline_result.auc
                and adaptive_result.brier_score is not None and baseline_result.brier_score is not None
                and adaptive_result.brier_score < baseline_result.brier_score
            ) else "baseline_better" if (
                adaptive_result.auc is not None and baseline_result.auc is not None
                and adaptive_result.auc < baseline_result.auc
                and adaptive_result.brier_score is not None and baseline_result.brier_score is not None
                and adaptive_result.brier_score > baseline_result.brier_score
            ) else "mixed_or_no_clear_improvement"
        ),
    })
    return report


def evaluate_l11_shadow_weights(
    observations: Iterable[LearningObservation],
    *,
    train_fraction: float = 0.7,
    min_train_samples: int = 20,
    min_test_samples: int = 5,
) -> dict:
    """Return separate chronological holdout reports for levels and analyzers."""
    rows = tuple(observations)
    return {
        "method": "chronological_holdout",
        "weights_applied_to_trading": False,
        "sample_count": len(rows),
        "level_scores": evaluate_feature_group(
            rows, "level_scores", train_fraction=train_fraction,
            min_train_samples=min_train_samples, min_test_samples=min_test_samples,
        ),
        "analyzer_scores": evaluate_feature_group(
            rows, "analyzer_scores", train_fraction=train_fraction,
            min_train_samples=min_train_samples, min_test_samples=min_test_samples,
        ),
    }
