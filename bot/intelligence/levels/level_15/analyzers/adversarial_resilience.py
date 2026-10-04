from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(l14) -> AnalyzerResult:
    contradiction = 1.0 - l14.score
    reliability = l14.data_reliability
    score = max(0.0, min(1.0, 0.70 * contradiction + 0.30 * reliability))
    return AnalyzerResult("adversarial_resilience", score, l14.confidence)
