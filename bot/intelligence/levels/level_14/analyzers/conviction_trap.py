from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level10_result, level12_result) -> AnalyzerResult:
    conviction = level10_result.conviction
    anomaly = level12_result.score
    readiness = level10_result.decision_readiness
    score = min(1.0, 0.50 * conviction * anomaly + 0.30 * anomaly + 0.20 * (1.0 - readiness))
    return AnalyzerResult("conviction_trap", score, min(level10_result.confidence, level12_result.confidence))
