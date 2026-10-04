from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level5, level6, level7, level8, level9):
    values = [x.score for x in (level5, level6, level7, level8, level9)]
    spread = max(values) - min(values)
    score = max(0.0, min(1.0, 1.0 - spread))
    confidence = min(x.confidence for x in (level5, level6, level7, level8, level9))
    return AnalyzerResult("cross_level_agreement", score, confidence, {"spread": spread})
