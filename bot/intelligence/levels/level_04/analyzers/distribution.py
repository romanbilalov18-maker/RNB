from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    returns = snapshot.historical_returns
    volumes = snapshot.historical_volume_ratios
    pairs = list(zip(returns, volumes))
    if len(pairs) < 5:
        return AnalyzerResult(
            "distribution", 0.0, 0.0,
            {"observations": len(pairs)},
            ("historical_price_volume_history_insufficient",),
        )
    total_volume = sum(max(0.0, volume) for _, volume in pairs)
    if total_volume <= 0:
        return AnalyzerResult("distribution", 0.0, 0.0, {"observations": len(pairs)}, ("historical_volume_not_available",))
    down_volume = sum(volume for change, volume in pairs if change < 0)
    up_volume = sum(volume for change, volume in pairs if change > 0)
    score = max(0.0, min(1.0, down_volume / total_volume))
    return AnalyzerResult(
        "distribution", score, min(1.0, len(pairs) / 20.0),
        {"down_volume_ratio": down_volume / total_volume,
         "up_volume_ratio": up_volume / total_volume,
         "net_directional_volume": (up_volume - down_volume) / total_volume,
         "observations": len(pairs)},
    )
