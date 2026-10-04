from dataclasses import dataclass, field
from typing import Any, Dict

from bot.intelligence.levels.level_01.models.level_01_result import Level1Result
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result
from bot.intelligence.levels.level_03.models.level_03_result import Level3Result
from bot.intelligence.levels.level_04.models.level_04_result import Level4Result
from bot.intelligence.levels.level_05.models.level_05_result import Level5Result
from bot.intelligence.levels.level_06.models.level_06_result import Level6Result
from bot.intelligence.levels.level_07.models.level_07_result import Level7Result
from bot.intelligence.levels.level_08.models.level_08_result import Level8Result
from bot.intelligence.levels.level_09.models.level_09_result import Level9Result
from bot.intelligence.levels.level_10.models.level_10_result import Level10Result


@dataclass(frozen=True)
class IntelligenceResult:
    symbol: str
    level_01: Level1Result
    level_02: Level2Result
    level_03: Level3Result
    level_04: Level4Result
    level_05: Level5Result
    level_06: Level6Result
    level_07: Level7Result
    level_08: Level8Result
    level_09: Level9Result
    level_10: Level10Result
    overall_score: float
    overall_confidence: float
    overall_consistency: float
    strengths: tuple[str, ...] = ()
    weaknesses: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (
            ("overall_score", self.overall_score),
            ("overall_confidence", self.overall_confidence),
            ("overall_consistency", self.overall_consistency),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
