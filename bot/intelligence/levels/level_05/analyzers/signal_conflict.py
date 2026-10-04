from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level3_result, level4_result) -> AnalyzerResult:
    directional_market = level3_result.score >= 0.5
    directional_behavior = level4_result.pressure_balance >= 0.5
    conflict = directional_market != directional_behavior
    score = 0.0 if conflict else 1.0
    return AnalyzerResult("signal_conflict", score, 0.9, {
        "conflict": conflict, "pressure_balance": level4_result.pressure_balance
    }, ["market_behavior_conflict"] if conflict else [])
