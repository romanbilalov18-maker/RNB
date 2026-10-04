from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level5_result) -> AnalyzerResult:
    upside = max(0.0, snapshot.momentum) + max(0.0, snapshot.price_change())
    score = min(1.0, upside * 5.0 + level5_result.score * 0.35)
    return AnalyzerResult("reward_potential", score, level5_result.confidence, {"upside_proxy": upside})
