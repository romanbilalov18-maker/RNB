from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(level8_result) -> AnalyzerResult:
    # Without the actual portfolio/universe, use relative-context quality as a proxy.
    score = min(1.0, max(0.0, 0.5 * level8_result.relative_consistency + 0.5 * level8_result.market_relative_strength))
    return AnalyzerResult("diversification_value", score, level8_result.confidence, {}, ["portfolio_composition_not_available"])
