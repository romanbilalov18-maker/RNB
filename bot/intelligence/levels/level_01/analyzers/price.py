import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def _is_finite_number(value: object) -> bool:
    """Reject bool explicitly: Python treats bool as a subclass of int."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    price = snapshot.price
    previous_price = snapshot.previous_price
    if previous_price is None:
        return AnalyzerResult("price", 0.0, 0.0, {"change": None}, ("previous_price_missing",))
    if (
        not _is_finite_number(price)
        or not _is_finite_number(previous_price)
        or price <= 0
        or previous_price <= 0
    ):
        return AnalyzerResult("price", 0.0, 0.0, {"change": None}, ("invalid_price_input",))
    change = (price - previous_price) / previous_price
    if not math.isfinite(change):
        return AnalyzerResult("price", 0.0, 0.0, {"change": None}, ("invalid_price_change",))
    score = min(max(0.5 + change * 5.0, 0.0), 1.0)
    return AnalyzerResult("price", score, 1.0, {"change": change})
