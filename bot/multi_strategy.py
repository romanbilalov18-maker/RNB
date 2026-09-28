from dataclasses import dataclass
from typing import Protocol

from bot.models import DecisionContext, SignalResult


class Strategy(Protocol):
    name: str

    def evaluate(self, context: DecisionContext) -> SignalResult:
        ...


@dataclass(frozen=True)
class StrategyDecision:
    strategy_name: str
    result: SignalResult


class MultiStrategyEngine:
    """Evaluates multiple strategies using the same immutable decision context."""

    def __init__(self, strategies: list[Strategy]) -> None:
        if not strategies:
            raise ValueError("at least one strategy is required")

        names = [strategy.name for strategy in strategies]
        if any(not name.strip() for name in names):
            raise ValueError("strategy names must not be empty")
        if len(set(names)) != len(names):
            raise ValueError("strategy names must be unique")

        self._strategies = tuple(strategies)

    @property
    def strategies(self) -> tuple[Strategy, ...]:
        return self._strategies

    def evaluate(self, context: DecisionContext) -> tuple[StrategyDecision, ...]:
        if not context.candles:
            raise ValueError("decision context must contain historical candles")

        return tuple(
            StrategyDecision(
                strategy_name=strategy.name,
                result=strategy.evaluate(context),
            )
            for strategy in self._strategies
        )

    def consensus(self, context: DecisionContext) -> SignalResult:
        decisions = self.evaluate(context)

        buy = [d.result for d in decisions if d.result.signal == "BUY"]
        sell = [d.result for d in decisions if d.result.signal == "SELL"]
        hold = [d.result for d in decisions if d.result.signal == "HOLD"]

        counts = {
            "BUY": len(buy),
            "SELL": len(sell),
            "HOLD": len(hold),
        }
        max_count = max(counts.values())
        winners = [signal for signal, count in counts.items() if count == max_count]

        if len(winners) != 1:
            return SignalResult(
                ticker=decisions[0].result.ticker,
                signal="HOLD",
                confidence=0.0,
                reason="No unique strategy consensus",
            )

        signal = winners[0]
        selected = buy if signal == "BUY" else sell if signal == "SELL" else hold
        confidence = sum(item.confidence for item in selected) / len(selected)

        return SignalResult(
            ticker=decisions[0].result.ticker,
            signal=signal,
            confidence=confidence,
            reason=f"Consensus from {counts[signal]}/{len(decisions)} strategies",
        )
