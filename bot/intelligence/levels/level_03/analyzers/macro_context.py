from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.levels.level_02.models.level_02_result import Level2Result


def analyze(snapshot: MarketSnapshot, level2: Level2Result) -> AnalyzerResult:
    """Neutral placeholder until a universal macro-data adapter exists."""
    return AnalyzerResult("macro_context", 0.5, 0.0, {"available": False}, ("macro_data_not_available",))
