import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level5_result, level6_result, level8_result) -> AnalyzerResult:
    results = (level5_result, level6_result, level8_result)
    if any(result is None for result in results):
        return AnalyzerResult("portfolio_consistency", 0.0, 0.0, {}, ["portfolio_consistency_inputs_not_available"])

    symbols = [getattr(result, "symbol", None) for result in results]
    if not all(isinstance(symbol, str) and symbol for symbol in symbols) or len(set(symbols)) != 1:
        return AnalyzerResult("portfolio_consistency", 0.0, 0.0, {"symbols": symbols}, ["portfolio_consistency_symbol_mismatch"])

    values = []
    confidences = []
    for result in results:
        try:
            score = float(result.score)
            confidence = float(result.confidence)
        except (TypeError, ValueError, AttributeError):
            return AnalyzerResult("portfolio_consistency", 0.0, 0.0, {}, ["portfolio_consistency_inputs_invalid"])
        if not math.isfinite(score) or not 0.0 <= score <= 1.0 or not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            return AnalyzerResult("portfolio_consistency", 0.0, 0.0, {}, ["portfolio_consistency_inputs_invalid"])
        values.append(score)
        confidences.append(confidence)

    spread = max(values) - min(values)
    return AnalyzerResult(
        "portfolio_consistency", max(0.0, min(1.0, 1.0 - spread)), min(confidences),
        {"spread": spread, "input_scores": values},
    )
