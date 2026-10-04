from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(results) -> AnalyzerResult:
    if not results:
        return AnalyzerResult("master_confidence", 0.0, 0.0)
    score = sum(r.score for r in results) / len(results)
    spread = max(r.score for r in results) - min(r.score for r in results)
    return AnalyzerResult("master_confidence", max(0.0, min(1.0, score * (1.0 - 0.5 * spread))), min(r.confidence for r in results))
