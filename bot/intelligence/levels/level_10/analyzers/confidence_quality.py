from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level5, level6, level7, level8, level9):
    values = [x.confidence for x in (level5, level6, level7, level8, level9)]
    score = sum(values) / len(values)
    return AnalyzerResult("confidence_quality", score, score, {})
