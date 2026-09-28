from dataclasses import dataclass
from typing import Sequence

from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline

from bot.training import TrainingSample


@dataclass(frozen=True)
class ModelEvaluation:
    sample_count: int
    accuracy: float
    precision: float
    recall: float
    f1: float
    roc_auc: float | None
    actual_positive_rate: float
    predicted_positive_rate: float


class ModelEvaluator:
    """Evaluate a trained classifier on a separate, chronological sample set."""

    def evaluate(
        self,
        model: Pipeline,
        samples: Sequence[TrainingSample],
    ) -> ModelEvaluation:
        if not samples:
            raise ValueError("samples must not be empty")

        x_values = [sample.values for sample in samples]
        y_true = [sample.target for sample in samples]
        predictions = model.predict(x_values)

        if len(predictions) != len(y_true):
            raise ValueError("model returned an unexpected number of predictions")

        y_pred = [int(value) for value in predictions]
        if any(value not in {0, 1} for value in y_true + y_pred):
            raise ValueError("evaluation targets and predictions must be binary")

        probabilities = None
        if hasattr(model, "predict_proba"):
            probabilities = model.predict_proba(x_values)[:, 1]

        roc_auc = None
        if len(set(y_true)) == 2 and probabilities is not None:
            roc_auc = float(roc_auc_score(y_true, probabilities))

        return ModelEvaluation(
            sample_count=len(samples),
            accuracy=float(accuracy_score(y_true, y_pred)),
            precision=float(precision_score(y_true, y_pred, zero_division=0)),
            recall=float(recall_score(y_true, y_pred, zero_division=0)),
            f1=float(f1_score(y_true, y_pred, zero_division=0)),
            roc_auc=roc_auc,
            actual_positive_rate=sum(y_true) / len(y_true),
            predicted_positive_rate=sum(y_pred) / len(y_pred),
        )
