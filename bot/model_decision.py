from bot.features import FeatureEngine
from bot.models import DecisionContext, SignalResult


class ModelDecisionEngine:
    """Convert a trained direction classifier into a trading signal."""

    def __init__(self, model, feature_engine: FeatureEngine | None = None) -> None:
        if not hasattr(model, "predict_proba"):
            raise ValueError("model must provide predict_proba")
        if not hasattr(model, "predict"):
            raise ValueError("model must provide predict")
        self.model = model
        self.feature_engine = feature_engine or FeatureEngine()

    def evaluate(self, context: DecisionContext) -> SignalResult:
        if not context.ticker.strip():
            raise ValueError("ticker must not be empty")
        if not context.candles:
            raise ValueError("decision context must contain historical candles")

        from bot.dataset import Dataset

        dataset = Dataset.from_candles(context.candles)
        feature = self.feature_engine.compute(dataset, len(dataset) - 1)
        values = self._feature_values(feature)

        if values is None:
            return SignalResult(
                ticker=context.ticker,
                signal="HOLD",
                confidence=0.0,
                reason="Model features are not warmed up",
            )

        probabilities = self.model.predict_proba([values])[0]
        classes = list(getattr(self.model, "classes_", ()))
        if not classes:
            classifier = getattr(self.model, "named_steps", {}).get("classifier")
            classes = list(getattr(classifier, "classes_", ()))
        if len(probabilities) != len(classes):
            raise ValueError("model probabilities and classes do not match")

        probability_by_class = {
            int(label): float(probability)
            for label, probability in zip(classes, probabilities)
        }
        positive_probability = probability_by_class.get(1)
        negative_probability = probability_by_class.get(0)
        if positive_probability is None or negative_probability is None:
            raise ValueError("model must support binary classes 0 and 1")

        signal = "BUY" if positive_probability >= 0.5 else "SELL"
        confidence = max(positive_probability, negative_probability)

        return SignalResult(
            ticker=context.ticker,
            signal=signal,
            confidence=confidence,
            reason=(
                "Model predicts next-candle direction: "
                f"BUY={positive_probability:.3f}, SELL={negative_probability:.3f}"
            ),
        )

    @staticmethod
    def _feature_values(feature) -> tuple[float, ...] | None:
        names = (
            "sma_fast", "sma_slow", "ema_fast", "ema_slow",
            "return_1", "momentum", "volatility", "rsi", "atr",
            "volume_ratio",
        )
        values = tuple(getattr(feature, name) for name in names)
        if any(value is None for value in values):
            return None
        return tuple(float(value) for value in values)
