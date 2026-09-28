from bot.models import DecisionContext, SignalResult


class Strategy:
    """Deterministic SMA direction strategy with crossover and persistent-trend signals."""

    def __init__(
        self,
        fast_period: int = 5,
        slow_period: int = 20,
        min_spread: float = 0.00005,
        confidence_scale: float = 0.0005,
    ):
        if fast_period <= 0 or slow_period <= 0:
            raise ValueError("Periods must be positive")
        if fast_period >= slow_period:
            raise ValueError("fast_period must be smaller than slow_period")
        if min_spread <= 0 or confidence_scale <= 0:
            raise ValueError("min_spread and confidence_scale must be positive")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.min_spread = min_spread
        self.confidence_scale = confidence_scale

    def evaluate(self, context: DecisionContext) -> SignalResult:
        prices = context.closes
        if len(prices) < self.slow_period + 1:
            return SignalResult(
                context.ticker, "HOLD", 0.0,
                f"Need at least {self.slow_period + 1} closes",
            )

        previous = prices[:-1]
        fast_prev = _sma(previous[-self.fast_period:])
        slow_prev = _sma(previous[-self.slow_period:])
        fast_now = _sma(prices[-self.fast_period:])
        slow_now = _sma(prices[-self.slow_period:])
        spread = (fast_now - slow_now) / slow_now

        if fast_prev <= slow_prev and fast_now > slow_now:
            return self._directional_result(context, "BUY", spread, "Fast SMA crossed above slow SMA")
        if fast_prev >= slow_prev and fast_now < slow_now:
            return self._directional_result(context, "SELL", spread, "Fast SMA crossed below slow SMA")

        if spread >= self.min_spread:
            return self._directional_result(context, "BUY", spread, "Fast SMA remains above slow SMA")
        if spread <= -self.min_spread:
            return self._directional_result(context, "SELL", spread, "Fast SMA remains below slow SMA")

        return SignalResult(context.ticker, "HOLD", 0.0, "SMA spread is below signal threshold")

    def _directional_result(
        self, context: DecisionContext, signal: str, spread: float, reason: str
    ) -> SignalResult:
        trend_strength = _trend_strength(context.closes, self.slow_period)
        spread_confidence = min(1.0, abs(spread) / self.confidence_scale)
        trend_confidence = min(1.0, trend_strength / self.confidence_scale)
        confidence = min(1.0, 0.5 * spread_confidence + 0.5 * trend_confidence)
        return SignalResult(context.ticker, signal, confidence, reason)


def _sma(values: tuple[float, ...] | list[float]) -> float:
    return sum(values) / len(values)


def _trend_strength(prices: tuple[float, ...], period: int) -> float:
    return abs(prices[-1] / prices[-period - 1] - 1.0)
