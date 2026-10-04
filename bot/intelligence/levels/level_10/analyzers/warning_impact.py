from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level5, level6, level7, level8, level9):
    warnings = set(level5.warnings + level6.warnings + level7.warnings + level8.warnings + level9.warnings)
    penalty = min(0.5, len(warnings) * 0.03)
    score = max(0.0, 1.0 - penalty)
    return AnalyzerResult("warning_impact", score, score, {"warning_count": len(warnings)})
