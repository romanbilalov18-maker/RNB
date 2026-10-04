from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(observations) -> AnalyzerResult:
    regimes = [item.regime for item in observations if item.regime]
    if not regimes:
        return AnalyzerResult("regime_adaptation", 0.5, 0.0, {}, ("regime_history_not_available",))
    distinct = len(set(regimes))
    coverage = min(1.0, distinct / 4.0)
    return AnalyzerResult("regime_adaptation", coverage, min(1.0, len(regimes) / 20.0), {"distinct_regimes": distinct})
