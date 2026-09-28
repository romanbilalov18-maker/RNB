from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from bot.dataset import Dataset
from bot.evaluation import ModelEvaluation, ModelEvaluator
from bot.training import TrainingEngine, TrainingSample


@dataclass(frozen=True)
class WalkForwardFold:
    """One chronological train/validation step."""

    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    train_size: int
    validation_size: int
    evaluation: ModelEvaluation


@dataclass(frozen=True)
class WalkForwardResult:
    """Complete walk-forward evaluation across chronological windows."""

    folds: tuple[WalkForwardFold, ...]

    @property
    def fold_count(self) -> int:
        return len(self.folds)

    @property
    def mean_accuracy(self) -> float:
        return _mean(fold.evaluation.accuracy for fold in self.folds)

    @property
    def mean_f1(self) -> float:
        return _mean(fold.evaluation.f1 for fold in self.folds)

    @property
    def mean_roc_auc(self) -> float | None:
        values = [
            fold.evaluation.roc_auc
            for fold in self.folds
            if fold.evaluation.roc_auc is not None
        ]
        return _mean(values) if values else None


class WalkForwardEngine:
    """Evaluate models on successive unseen time windows without future leakage."""

    def __init__(
        self,
        training_engine: TrainingEngine | None = None,
        evaluator: ModelEvaluator | None = None,
    ):
        self.training_engine = training_engine or TrainingEngine()
        self.evaluator = evaluator or ModelEvaluator()

    def run(
        self,
        dataset: Dataset,
        train_size: int,
        validation_size: int,
        step_size: int,
        expanding: bool = True,
    ) -> WalkForwardResult:
        return self.run_samples(
            self.training_engine.build_samples(dataset),
            train_size,
            validation_size,
            step_size,
            expanding,
        )

    def run_samples(
        self,
        samples: Sequence[TrainingSample],
        train_size: int,
        validation_size: int,
        step_size: int,
        expanding: bool = True,
    ) -> WalkForwardResult:
        if train_size <= 0:
            raise ValueError("train_size must be positive")
        if validation_size <= 0:
            raise ValueError("validation_size must be positive")
        if step_size <= 0:
            raise ValueError("step_size must be positive")

        samples = tuple(samples)
        if len(samples) < train_size + validation_size:
            raise ValueError("not enough samples for the requested walk-forward windows")

        folds: list[WalkForwardFold] = []
        start = 0

        while start + train_size + validation_size <= len(samples):
            train_end_index = start + train_size
            validation_end_index = train_end_index + validation_size

            if expanding:
                train_samples = samples[:train_end_index]
            else:
                train_samples = samples[start:train_end_index]

            validation_samples = samples[train_end_index:validation_end_index]
            model = self.training_engine.fit_samples(train_samples)
            evaluation = self.evaluator.evaluate(model, validation_samples)

            folds.append(
                WalkForwardFold(
                    train_start=train_samples[0].timestamp,
                    train_end=train_samples[-1].timestamp,
                    validation_start=validation_samples[0].timestamp,
                    validation_end=validation_samples[-1].timestamp,
                    train_size=len(train_samples),
                    validation_size=len(validation_samples),
                    evaluation=evaluation,
                )
            )

            start += step_size

        if not folds:
            raise ValueError("walk-forward configuration produced no folds")

        return WalkForwardResult(folds=tuple(folds))


def _mean(values) -> float:
    values = tuple(values)
    if not values:
        return 0.0
    return sum(values) / len(values)
