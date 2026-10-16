import math
from bot.intelligence.core.models.analysis_result import AnalyzerResult


def number(value, *, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    value = float(value)
    if minimum is not None and value < minimum:
        return None
    if maximum is not None and value > maximum:
        return None
    return value


def result_or_unavailable(name, warnings, metrics=None):
    return AnalyzerResult(name, 0.0, 0.0, metrics or {}, tuple(dict.fromkeys(warnings)))


def level5_context(snapshot, result):
    warnings = []
    if result is None:
        return ["level5_context_not_available"]
    symbol = getattr(result, "symbol", None)
    snapshot_symbol = getattr(snapshot, "symbol", None)
    if not isinstance(symbol, str) or not symbol:
        warnings.append("level5_symbol_not_available")
    elif not isinstance(snapshot_symbol, str) or symbol != snapshot_symbol:
        warnings.append("level5_symbol_mismatch")
    return warnings


def confidence(result):
    return number(getattr(result, "confidence", None), minimum=0.0, maximum=1.0)
