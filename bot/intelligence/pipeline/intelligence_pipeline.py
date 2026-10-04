from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.level_01_engine import aggregate as aggregate_level_01
from bot.intelligence.levels.level_01.level_01_engine import analyze as analyze_level_01
from bot.intelligence.levels.level_01.models.level_01_result import Level1Result
from bot.intelligence.levels.level_02.level_02_engine import analyze as analyze_level_02
from bot.intelligence.levels.level_03.level_03_engine import analyze as analyze_level_03
from bot.intelligence.levels.level_04.level_04_engine import Level4Engine
from bot.intelligence.levels.level_05.level_05_engine import Level5Engine
from bot.intelligence.levels.level_06.level_06_engine import Level6Engine
from bot.intelligence.levels.level_07.level_07_engine import Level7Engine
from bot.intelligence.levels.level_08.level_08_engine import Level8Engine
from bot.intelligence.levels.level_09.level_09_engine import Level9Engine
from bot.intelligence.levels.level_10.level_10_engine import Level10Engine
from bot.intelligence.levels.level_11.level_11_engine import Level11Engine
from bot.intelligence.levels.level_11.models.learning_observation import LearningObservation
from bot.intelligence.levels.level_12.level_12_engine import Level12Engine

from .intelligence_result import IntelligenceResult


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, value))


class IntelligencePipeline:
    """Run Levels 1-12 without trading side effects."""

    def __init__(self, learning_observations: tuple[LearningObservation, ...] = ()) -> None:
        self.learning_observations = learning_observations
        self.level_04 = Level4Engine()
        self.level_05 = Level5Engine()
        self.level_06 = Level6Engine()
        self.level_07 = Level7Engine()
        self.level_08 = Level8Engine()
        self.level_09 = Level9Engine()
        self.level_10 = Level10Engine()
        self.level_11 = Level11Engine()
        self.level_12 = Level12Engine()

    def analyze(self, snapshot: MarketSnapshot) -> IntelligenceResult:
        analyzers = analyze_level_01(snapshot)
        confidence = sum(r.confidence for r in analyzers) / len(analyzers) if analyzers else 0.0
        consistency = 1.0 - (max(r.score for r in analyzers) - min(r.score for r in analyzers)) if analyzers else 0.0
        level_01 = Level1Result(
            symbol=snapshot.symbol,
            score=aggregate_level_01(analyzers),
            confidence=_bounded(confidence),
            consistency=_bounded(consistency),
            analyzer_results=analyzers,
            strengths=tuple(r.analyzer for r in analyzers if r.score >= 0.70),
            weaknesses=tuple(r.analyzer for r in analyzers if r.score <= 0.30),
            warnings=tuple(dict.fromkeys(w for r in analyzers for w in r.warnings)),
            metadata={"version": "1.0"},
        )
        level_02 = analyze_level_02(snapshot, level_01)
        level_03 = analyze_level_03(snapshot, level_02)
        level_04 = self.level_04.analyze(snapshot, level_03)
        level_05 = self.level_05.analyze(snapshot, level_02, level_03, level_04)
        level_06 = self.level_06.analyze(snapshot, level_05)
        level_07 = self.level_07.analyze(snapshot, level_03, level_04, level_05, level_06)
        level_08 = self.level_08.analyze(snapshot, level_03, level_04, level_07)
        level_09 = self.level_09.analyze(snapshot, level_05, level_06, level_08)
        level_10 = self.level_10.analyze(snapshot, level_05, level_06, level_07, level_08, level_09)
        level_11 = self.level_11.analyze(snapshot.symbol, self.learning_observations)
        level_12 = self.level_12.analyze(snapshot, level_04, level_07, level_10)

        warnings = tuple(dict.fromkeys(
            list(level_01.warnings) + list(level_02.warnings) + list(level_03.warnings) +
            list(level_04.warnings) + list(level_05.warnings) + list(level_06.warnings) +
            list(level_07.warnings) + list(level_08.warnings) + list(level_09.warnings) +
            list(level_10.warnings) + list(level_11.warnings) + list(level_12.warnings)
        ))
        return IntelligenceResult(
            symbol=snapshot.symbol,
            level_01=level_01, level_02=level_02, level_03=level_03,
            level_04=level_04, level_05=level_05, level_06=level_06,
            level_07=level_07, level_08=level_08, level_09=level_09,
            level_10=level_10, level_11=level_11, level_12=level_12,
            overall_score=level_10.score,
            overall_confidence=level_10.confidence,
            overall_consistency=level_10.consistency,
            strengths=tuple(dict.fromkeys(list(level_10.strengths) + list(level_09.strengths) + list(level_08.strengths))),
            weaknesses=tuple(dict.fromkeys(list(level_10.weaknesses) + list(level_09.weaknesses) + list(level_08.weaknesses))),
            warnings=warnings,
            metadata={"version": "1.0", "levels": 12, "learning_samples": len(self.learning_observations)},
        )
