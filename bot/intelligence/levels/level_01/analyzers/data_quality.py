from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    fields = (snapshot.price, snapshot.previous_price, snapshot.volume, snapshot.average_volume)
    available = sum(value is not None for value in fields)
    confidence = available / len(fields)
    return AnalyzerResult("data_quality", confidence, confidence, {"available_fields": available})
