from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(l11) -> AnalyzerResult:
    score = (l11.outcome_quality + l11.level_effectiveness + l11.analyzer_effectiveness + l11.learning_confidence) / 4.0
    return AnalyzerResult("learning_quality", score, l11.confidence)
