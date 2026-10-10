from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Iterable


@dataclass(frozen=True)
class TradingDecision:
    ticker: str
    action: str
    reason: str
    score: float | None = None
    confidence: float | None = None
    consistency: float | None = None


class DecisionEngine:
    """Convert L1-L15 aggregate metrics into recommendations, without execution."""

    def __init__(
        self,
        min_buy_score: float = 0.60,
        min_confidence: float = 0.50,
        min_consistency: float = 0.50,
        max_sell_score: float = 0.30,
        min_sell_confidence: float = 0.60,
    ) -> None:
        values = {
            "min_buy_score": min_buy_score,
            "min_confidence": min_confidence,
            "min_consistency": min_consistency,
            "max_sell_score": max_sell_score,
            "min_sell_confidence": min_sell_confidence,
        }
        for name, value in values.items():
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be a finite number between 0 and 1")
        if max_sell_score >= min_buy_score:
            raise ValueError("max_sell_score must be below min_buy_score")

        self.min_buy_score = min_buy_score
        self.min_confidence = min_confidence
        self.min_consistency = min_consistency
        self.max_sell_score = max_sell_score
        self.min_sell_confidence = min_sell_confidence

    @staticmethod
    def _metrics(intelligence) -> tuple[float, float, float] | None:
        if intelligence is None:
            return None
        try:
            score = float(intelligence.overall_score)
            confidence = float(intelligence.overall_confidence)
            consistency = float(intelligence.overall_consistency)
        except (AttributeError, TypeError, ValueError, OverflowError):
            return None
        values = (score, confidence, consistency)
        if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in values):
            return None
        return values

    def decide(self, ticker: str, intelligence, *, is_held: bool = False) -> TradingDecision:
        metrics = self._metrics(intelligence)
        if metrics is None:
            return TradingDecision(ticker, "WAIT", "нет корректного результата Intelligence")

        score, confidence, consistency = metrics
        common = {
            "score": score,
            "confidence": confidence,
            "consistency": consistency,
        }

        # A SELL is only a recommendation. PositionManager remains authoritative
        # for actual virtual exits; this class never submits or executes orders.
        if is_held:
            if score <= self.max_sell_score and confidence >= self.min_sell_confidence:
                return TradingDecision(
                    ticker,
                    "SELL",
                    "слабый сигнал Intelligence; требуется проверка существующими правилами PositionManager",
                    **common,
                )
            return TradingDecision(
                ticker, "HOLD", "сигнал Intelligence не подтверждает продажу", **common
            )

        if confidence < self.min_confidence:
            return TradingDecision(
                ticker, "WAIT", "недостаточная уверенность", **common
            )
        if consistency < self.min_consistency:
            return TradingDecision(
                ticker, "WAIT", "недостаточная согласованность уровней", **common
            )
        if score >= self.min_buy_score:
            return TradingDecision(
                ticker, "BUY", "пройдены пороги оценки, уверенности и согласованности", **common
            )
        return TradingDecision(
            ticker, "WAIT", "оценка ниже порога покупки", **common
        )

    def evaluate(
        self,
        intelligence_results: Mapping[str, object],
        held_tickers: Iterable[str] = (),
    ) -> dict[str, TradingDecision]:
        held = set(held_tickers)
        return {
            ticker: self.decide(ticker, result, is_held=ticker in held)
            for ticker, result in intelligence_results.items()
        }
