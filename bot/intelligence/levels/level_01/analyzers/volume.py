import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    volume = snapshot.volume
    average_volume = snapshot.average_volume
    if volume is None or average_volume is None:
        return AnalyzerResult("volume", 0.0, 0.0, {"ratio": None}, ("volume_missing",))
    if (
        isinstance(volume, bool)
        or isinstance(average_volume, bool)
        or not isinstance(volume, (int, float))
        or not isinstance(average_volume, (int, float))
        or not math.isfinite(volume)
        or not math.isfinite(average_volume)
        or volume < 0
        or average_volume <= 0
    ):
        return AnalyzerResult("volume", 0.0, 0.0, {"ratio": None}, ("invalid_volume",))
    ratio = volume / average_volume
    if not math.isfinite(ratio):
        return AnalyzerResult("volume", 0.0, 0.0, {"ratio": None}, ("invalid_volume_ratio",))
    score = min(max(ratio / 2.0, 0.0), 1.0)
    return AnalyzerResult("volume", score, 1.0, {"ratio": ratio})
