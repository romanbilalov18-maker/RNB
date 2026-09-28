from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from bot.models import HistoricalCandle


@dataclass(frozen=True)
class Dataset:
    """Chronologically ordered, validated historical market dataset."""

    candles: tuple[HistoricalCandle, ...]

    def __post_init__(self) -> None:
        timestamps = [candle.timestamp for candle in self.candles]

        if timestamps != sorted(timestamps):
            raise ValueError("Dataset candles must be sorted chronologically")
        if len(timestamps) != len(set(timestamps)):
            raise ValueError("Dataset candles must not contain duplicate timestamps")

        for candle in self.candles:
            if not candle.is_valid():
                raise ValueError("Dataset contains an invalid candle")

    @classmethod
    def from_candles(
        cls,
        candles: Iterable[HistoricalCandle],
    ) -> "Dataset":
        from bot.historical import normalize_candles

        return cls(tuple(normalize_candles(candles)))

    @property
    def start(self) -> datetime | None:
        return self.candles[0].timestamp if self.candles else None

    @property
    def end(self) -> datetime | None:
        return self.candles[-1].timestamp if self.candles else None

    def split(self, train_ratio: float = 0.8) -> tuple["Dataset", "Dataset"]:
        """Split chronologically so training never contains future observations."""
        if not 0 < train_ratio < 1:
            raise ValueError("train_ratio must be between 0 and 1")

        split_index = int(len(self.candles) * train_ratio)
        if split_index <= 0 or split_index >= len(self.candles):
            raise ValueError("Dataset is too small for the requested split")

        train = Dataset(self.candles[:split_index])
        test = Dataset(self.candles[split_index:])

        if train.end >= test.start:
            raise ValueError("Training data must end before test data starts")

        return train, test

    def closes(self) -> tuple[float, ...]:
        return tuple(candle.close for candle in self.candles)

    def __len__(self) -> int:
        return len(self.candles)
