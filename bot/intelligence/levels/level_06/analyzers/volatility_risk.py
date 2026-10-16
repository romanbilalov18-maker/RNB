from bot.intelligence.core.models.analysis_result import AnalyzerResult
from ._validation import number, result_or_unavailable


def analyze(snapshot) -> AnalyzerResult:
    raw = getattr(snapshot, "volatility", None)
    volatility = number(raw, minimum=0.0)
    if volatility is None:
        warning = "volatility_data_not_available" if raw is None else "volatility_input_invalid"
        return result_or_unavailable("volatility_risk", [warning])
    score = min(1.0, volatility * 12.0)
    confidence = 0.85 if volatility <= 0.25 else 0.65
    return AnalyzerResult("volatility_risk", score, confidence, {"volatility": volatility})
