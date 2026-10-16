import math

from bot.intelligence.core.models.analysis_result import AnalyzerResult
from bot.intelligence.core.models.market_snapshot import MarketSnapshot


def analyze(snapshot: MarketSnapshot) -> AnalyzerResult:
    """Measure usable inputs; distinguish missing data from invalid data."""
    fields = {
        "price": (snapshot.price, lambda value: value > 0),
        "previous_price": (snapshot.previous_price, lambda value: value > 0),
        "volume": (snapshot.volume, lambda value: value >= 0),
        "average_volume": (snapshot.average_volume, lambda value: value > 0),
        "volatility": (snapshot.volatility, lambda value: value >= 0),
        "momentum": (snapshot.momentum, lambda value: True),
        "liquidity": (snapshot.liquidity, lambda value: 0.0 <= value <= 1.0),
    }

    available = 0
    missing = []
    invalid = []
    for name, (value, valid_range) in fields.items():
        if value is None:
            missing.append(name)
            continue
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not valid_range(value)
        ):
            invalid.append(name)
            continue
        available += 1

    confidence = available / len(fields)
    warnings = tuple(
        [f"missing_{name}" for name in missing]
        + [f"invalid_{name}" for name in invalid]
    )
    return AnalyzerResult(
        "data_quality",
        confidence,
        confidence,
        {
            "available_fields": available,
            "total_fields": len(fields),
            "missing_fields": tuple(missing),
            "invalid_fields": tuple(invalid),
            "completeness": confidence,
        },
        warnings,
    )
