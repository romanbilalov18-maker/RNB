from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_01.level_01_engine import aggregate as aggregate_level_01, analyze as analyze_level_01
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
from bot.intelligence.levels.level_13.level_13_engine import Level13Engine
from bot.intelligence.levels.level_14.level_14_engine import Level14Engine
from .intelligence_result import IntelligenceResult

def _bounded(value: float) -> float:
    return max(0.0, min(1.0, value))

class IntelligencePipeline:
    """Run Levels 1-14 without trading side effects."""
    def __init__(self, learning_observations: tuple[LearningObservation, ...] = ()) -> None:
        self.learning_observations = learning_observations
        self.level_04, self.level_05, self.level_06 = Level4Engine(), Level5Engine(), Level6Engine()
        self.level_07, self.level_08, self.level_09 = Level7Engine(), Level8Engine(), Level9Engine()
        self.level_10, self.level_11, self.level_12, self.level_13, self.level_14 = Level10Engine(), Level11Engine(), Level12Engine(), Level13Engine(), Level14Engine()

    def analyze(self, snapshot: MarketSnapshot) -> IntelligenceResult:
        a = analyze_level_01(snapshot)
        l1 = Level1Result(snapshot.symbol, aggregate_level_01(a), _bounded(sum(r.confidence for r in a)/len(a)) if a else 0.0, _bounded(1.0-(max(r.score for r in a)-min(r.score for r in a))) if a else 0.0, a, tuple(r.analyzer for r in a if r.score>=.70), tuple(r.analyzer for r in a if r.score<=.30), tuple(dict.fromkeys(w for r in a for w in r.warnings)), {"version":"1.0"})
        l2 = analyze_level_02(snapshot,l1); l3 = analyze_level_03(snapshot,l2)
        l4 = self.level_04.analyze(snapshot,l3); l5 = self.level_05.analyze(snapshot,l2,l3,l4)
        l6 = self.level_06.analyze(snapshot,l5); l7 = self.level_07.analyze(snapshot,l3,l4,l5,l6)
        l8 = self.level_08.analyze(snapshot,l3,l4,l7); l9 = self.level_09.analyze(snapshot,l5,l6,l8)
        l10 = self.level_10.analyze(snapshot,l5,l6,l7,l8,l9); l11 = self.level_11.analyze(snapshot.symbol,self.learning_observations)
        l12 = self.level_12.analyze(snapshot,l4,l7,l10); l13 = self.level_13.analyze(snapshot,l6,l7,l10,l12)
        l14 = self.level_14.analyze(l6,l10,l12,l13)
        warnings = tuple(dict.fromkeys(sum((list(x.warnings) for x in (l1,l2,l3,l4,l5,l6,l7,l8,l9,l10,l11,l12,l13,l14)), [])))
        return IntelligenceResult(snapshot.symbol,l1,l2,l3,l4,l5,l6,l7,l8,l9,l10,l11,l12,l13,l14,l10.score,l10.confidence,l10.consistency,tuple(dict.fromkeys(list(l10.strengths)+list(l9.strengths)+list(l8.strengths))),tuple(dict.fromkeys(list(l10.weaknesses)+list(l9.weaknesses)+list(l8.weaknesses))),warnings,{"version":"1.0","levels":14,"learning_samples":len(self.learning_observations)})
