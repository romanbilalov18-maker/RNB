import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    returns = snapshot.historical_returns
    volumes = snapshot.historical_volume_ratios
    if len(returns) != len(volumes):
        return AnalyzerResult(
            "accumulation", 0.0, 0.0,
            {"return_observations": len(returns), "volume_observations": len(volumes)},
            ("historical_price_volume_history_misaligned",),
        )

    pairs = []
    invalid = 0
    for change, volume in zip(returns, volumes):
        if not isinstance(change, (int, float)) or not math.isfinite(change):
            invalid += 1
            continue
        if not isinstance(volume, (int, float)) or not math.isfinite(volume) or volume < 0:
            invalid += 1
            continue
        pairs.append((change, volume))

    if invalid:
        warning = ("historical_price_volume_invalid_observations",)
    else:
        warning = ()
    if len(pairs) < 5:
        return AnalyzerResult(
            "accumulation", 0.0, 0.0, {"observations": len(pairs), "invalid_observations": invalid},
            tuple(dict.fromkeys(warning + ("historical_price_volume_history_insufficient",))),
        )

    total_volume = sum(volume for _, volume in pairs)
    if not math.isfinite(total_volume) or total_volume <= 0:
        return AnalyzerResult(
            "accumulation", 0.0, 0.0, {"observations": len(pairs), "invalid_observations": invalid},
            tuple(dict.fromkeys(warning + ("historical_volume_not_available",))),
        )
    up_volume = sum(volume for change, volume in pairs if change > 0)
    down_volume = sum(volume for change, volume in pairs if change < 0)
    score = max(0.0, min(1.0, up_volume / total_volume))
    return AnalyzerResult(
        "accumulation", score, min(1.0, len(pairs) / 20.0),
        {"up_volume_ratio": up_volume / total_volume,
         "down_volume_ratio": down_volume / total_volume,
         "net_directional_volume": (up_volume - down_volume) / total_volume,
         "observations": len(pairs), "invalid_observations": invalid}, warning,
    )
