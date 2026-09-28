from dataclasses import dataclass
from time import sleep
from typing import Callable

from bot.app import TradingBot


@dataclass(frozen=True)
class CycleResult:
    cycle: int
    status: str
    signal: str
    reason: str
    decision_diagnostics: dict | None = None


class TradingRunner:
    """Runs repeated strategy/evaluation cycles.

    The runner supports Sandbox execution.
    Live execution remains disabled.
    """

    def __init__(
        self,
        bot: TradingBot,
        interval_seconds: float = 60.0,
        sleep_fn: Callable[[float], None] = sleep,
    ):
        if interval_seconds < 0:
            raise ValueError("interval_seconds must be non-negative")

        self.bot = bot
        self.interval_seconds = interval_seconds
        self.sleep_fn = sleep_fn

    def run(self, cycles: int) -> list[CycleResult]:
        if cycles <= 0:
            raise ValueError("cycles must be positive")

        results: list[CycleResult] = []

        for cycle in range(1, cycles + 1):
            result = self.bot.execute_signal()
            results.append(
                CycleResult(
                    cycle=cycle,
                    status=result["status"],
                    signal=result.get("signal", "UNKNOWN"),
                    reason=result.get("reason", result["status"]),
                    decision_diagnostics=result.get("decision_diagnostics"),
                )
            )

            if cycle < cycles:
                self.sleep_fn(self.interval_seconds)

        return results
