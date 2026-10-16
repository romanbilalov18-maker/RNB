import math


def normalized_value(result, field):
    """Return a finite normalized metric, or None when unavailable/invalid."""
    if result is None:
        return None
    value = getattr(result, field, None)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    if not 0.0 <= value <= 1.0:
        return None
    return float(value)


def context_warnings(snapshot, *results):
    warnings = []
    known_symbols = []
    for index, result in enumerate(results, start=2):
        if result is None:
            warnings.append(f"level{index}_context_not_available")
            continue
        symbol = getattr(result, "symbol", None)
        if not isinstance(symbol, str) or not symbol:
            warnings.append(f"level{index}_symbol_not_available")
        else:
            known_symbols.append((index, symbol))
            if snapshot is not None and symbol != getattr(snapshot, "symbol", None):
                warnings.append(f"level{index}_symbol_mismatch")
    if snapshot is None and len({symbol for _, symbol in known_symbols}) > 1:
        warnings.append("input_symbol_mismatch")
    return warnings


def unavailable(name, warnings, metrics=None):
    from bot.intelligence.core.models.analysis_result import AnalyzerResult
    return AnalyzerResult(name, 0.0, 0.0, metrics or {}, tuple(dict.fromkeys(warnings)))
