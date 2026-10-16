import math
from bot.intelligence.core.models.analysis_result import AnalyzerResult


def finite(value, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    value = float(value)
    if minimum is not None and value < minimum:
        return None
    if maximum is not None and value > maximum:
        return None
    return value


def unavailable(name, warnings, metrics=None):
    return AnalyzerResult(name, 0.0, 0.0, metrics or {}, tuple(dict.fromkeys(warnings)))


def upstream_context(snapshot, result, name):
    if result is None:
        return [f"{name}_context_not_available"]
    if hasattr(result, "symbol"):
        symbol = getattr(result, "symbol")
        expected = getattr(snapshot, "symbol", None)
        if not isinstance(symbol, str) or not symbol:
            return [f"{name}_symbol_not_available"]
        if not isinstance(expected, str) or symbol != expected:
            return [f"{name}_symbol_mismatch"]
    return []


def metric(result, name, minimum=0.0, maximum=1.0):
    return finite(getattr(result, name, None), minimum, maximum)
