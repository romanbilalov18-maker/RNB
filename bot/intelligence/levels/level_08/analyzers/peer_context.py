from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level4_result) -> AnalyzerResult:
    score = max(0.0, min(1.0, level4_result.liquidity_behavior * 0.6 + level4_result.pressure_balance * 0.4))
    return AnalyzerResult("peer_context", score, 0.35, {}, ["peer_universe_not_available"])
