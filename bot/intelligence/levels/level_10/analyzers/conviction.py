from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level5, level6, level7, level8, level9):
    score = sum(x.score for x in (level5, level6, level7, level8, level9)) / 5.0
    confidence = sum(x.confidence for x in (level5, level6, level7, level8, level9)) / 5.0
    return AnalyzerResult("conviction", score, confidence, {})
