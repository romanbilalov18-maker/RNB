from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot, level6_result) -> AnalyzerResult:
    returns = snapshot.historical_returns
    if len(returns) < 8:
        return AnalyzerResult("momentum_acceleration", 0.0, 0.0, {"observations": len(returns)}, ("historical_momentum_series_insufficient",))
    recent = sum(returns[-3:]) / 3.0
    prior = sum(returns[-6:-3]) / 3.0
    acceleration = recent - prior
    score = max(0.0, min(1.0, 0.5 + acceleration * 8.0))
    return AnalyzerResult("momentum_acceleration", score, min(1.0, len(returns) / 30.0), {"recent_mean_return": recent, "prior_mean_return": prior, "acceleration": acceleration, "observations": len(returns)})
