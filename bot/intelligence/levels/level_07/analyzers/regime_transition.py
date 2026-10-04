from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level3_result) -> AnalyzerResult:
    momentum_direction = snapshot.momentum >= 0.0
    market_direction = level3_result.score >= 0.5
    transition = momentum_direction != market_direction
    score = 0.8 if transition else 0.2
    return AnalyzerResult("regime_transition", score, level3_result.confidence, {"transition_detected": transition})
