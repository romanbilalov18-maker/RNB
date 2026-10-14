from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level5_result) -> AnalyzerResult:
    returns = sorted(value for value in snapshot.historical_returns if value > 0)
    if len(snapshot.historical_returns) < 10 or not returns:
        return AnalyzerResult("reward_potential", 0.0, 0.0, {"observations": len(snapshot.historical_returns), "positive_return_observations": len(returns)}, ("historical_upside_distribution_insufficient",))
    index = min(len(returns) - 1, int(0.9 * (len(returns) - 1)))
    upside_quantile = returns[index]
    score = max(0.0, min(1.0, upside_quantile / 0.05))
    return AnalyzerResult("reward_potential", score, min(1.0, len(snapshot.historical_returns) / 30.0), {"historical_positive_return_p90": upside_quantile, "observations": len(snapshot.historical_returns), "method": "empirical_positive_daily_return_quantile"})
