from bot.intelligence.core.models.analysis_result import AnalyzerResult
from ._validation import normalized_value, context_warnings, unavailable


def analyze(level3_result, level4_result) -> AnalyzerResult:
    warnings = context_warnings(None, level3_result, level4_result)
    market = normalized_value(level3_result, "score")
    pressure = normalized_value(level4_result, "pressure_balance")
    c3 = normalized_value(level3_result, "confidence")
    c4 = normalized_value(level4_result, "confidence")
    if warnings or None in (market, pressure, c3, c4):
        return unavailable("signal_conflict", warnings + ["signal_conflict_inputs_invalid"])
    conflict = (market >= 0.5) != (pressure >= 0.5)
    return AnalyzerResult("signal_conflict", 0.0 if conflict else 1.0, (c3 + c4) / 2.0, {
        "conflict": conflict, "level3_score": market, "pressure_balance": pressure,
    }, ("market_behavior_conflict",) if conflict else ())
