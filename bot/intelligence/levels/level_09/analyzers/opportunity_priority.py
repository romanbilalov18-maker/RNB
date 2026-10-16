import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level5_result, level6_result, level8_result) -> AnalyzerResult:
    results = (level5_result, level6_result, level8_result)
    if any(result is None for result in results):
        return AnalyzerResult("opportunity_priority", 0.0, 0.0, {}, ["opportunity_inputs_not_available"])

    symbols = [getattr(result, "symbol", None) for result in results]
    if not all(isinstance(symbol, str) and symbol for symbol in symbols) or len(set(symbols)) != 1:
        return AnalyzerResult("opportunity_priority", 0.0, 0.0, {"symbols": symbols}, ["opportunity_input_symbol_mismatch"])

    values = []
    for result, field in ((level5_result, "score"), (level6_result, "risk_reward"), (level8_result, "score")):
        try:
            score = float(getattr(result, field))
            confidence = float(getattr(result, "confidence"))
        except (TypeError, ValueError, AttributeError):
            return AnalyzerResult("opportunity_priority", 0.0, 0.0, {}, ["opportunity_inputs_invalid"])
        if not math.isfinite(score) or not 0.0 <= score <= 1.0 or not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            return AnalyzerResult("opportunity_priority", 0.0, 0.0, {}, ["opportunity_inputs_invalid"])
        values.append((score, confidence))

    score = sum(value * weight for (value, _), weight in zip(values, (0.35, 0.35, 0.30)))
    confidence = min(conf for _, conf in values)
    return AnalyzerResult(
        "opportunity_priority", max(0.0, min(1.0, score)), confidence,
        {"level5_signal": values[0][0], "level6_risk_reward": values[1][0], "level8_relative_context": values[2][0]},
    )
