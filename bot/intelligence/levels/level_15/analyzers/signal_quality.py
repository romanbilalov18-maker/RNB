from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(l10) -> AnalyzerResult:
    score = (l10.conviction + l10.cross_level_agreement + l10.confidence_quality) / 3.0
    return AnalyzerResult("signal_quality", score, l10.confidence)
