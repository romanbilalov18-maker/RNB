import math
from numbers import Real

from bot.intelligence.core.models.analysis_result import AnalyzerResult


def _finite_number(value) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def analyze(snapshot) -> AnalyzerResult:
    fields = (
        "previous_price", "volume", "average_volume", "volatility",
        "momentum", "liquidity",
    )
    missing_fields = [name for name in fields if getattr(snapshot, name, None) is None]
    invalid_fields = []

    numeric_fields = (
        "price", "previous_price", "volume", "average_volume",
        "volatility", "momentum", "liquidity",
    )
    for name in numeric_fields:
        value = getattr(snapshot, name, None)
        if value is not None and not _finite_number(value):
            invalid_fields.append(name)

    price = getattr(snapshot, "price", None)
    if price is None or (_finite_number(price) and price <= 0):
        invalid_fields.append("price")
    previous_price = getattr(snapshot, "previous_price", None)
    if _finite_number(previous_price) and previous_price <= 0:
        invalid_fields.append("previous_price")
    volume = getattr(snapshot, "volume", None)
    if _finite_number(volume) and volume < 0:
        invalid_fields.append("volume")
    average_volume = getattr(snapshot, "average_volume", None)
    if _finite_number(average_volume) and average_volume <= 0:
        invalid_fields.append("average_volume")
    volatility = getattr(snapshot, "volatility", None)
    if _finite_number(volatility) and volatility < 0:
        invalid_fields.append("volatility")
    liquidity = getattr(snapshot, "liquidity", None)
    if _finite_number(liquidity) and not 0.0 <= liquidity <= 1.0:
        invalid_fields.append("liquidity")

    ohlc = {
        "open_price": getattr(snapshot, "open_price", None),
        "high_price": getattr(snapshot, "high_price", None),
        "low_price": getattr(snapshot, "low_price", None),
        "close_price": getattr(snapshot, "close_price", None),
    }
    supplied_ohlc = {name: value for name, value in ohlc.items() if value is not None}
    if supplied_ohlc and len(supplied_ohlc) != len(ohlc):
        invalid_fields.append("incomplete_ohlc")
    elif len(supplied_ohlc) == len(ohlc):
        if any(not _finite_number(value) for value in supplied_ohlc.values()):
            invalid_fields.append("nonfinite_or_non_numeric_ohlc")
        elif any(value <= 0 for value in supplied_ohlc.values()):
            invalid_fields.append("nonpositive_ohlc")
        elif (
            snapshot.low_price > min(snapshot.open_price, snapshot.close_price)
            or snapshot.high_price < max(snapshot.open_price, snapshot.close_price)
            or snapshot.low_price > snapshot.high_price
        ):
            invalid_fields.append("inconsistent_ohlc")

    total_checks = len(fields) + 1 + (1 if supplied_ohlc else 0)
    anomaly_count = len(set(missing_fields)) + len(set(invalid_fields))
    score = min(1.0, anomaly_count / total_checks)
    confidence = max(0.0, 1.0 - len(missing_fields) / len(fields))
    warnings = []
    if missing_fields:
        warnings.append("market_snapshot_incomplete")
    if invalid_fields:
        warnings.append("market_snapshot_invalid_values")
    return AnalyzerResult(
        "data_anomaly", score, confidence,
        {"missing_fields": len(missing_fields), "missing_field_names": missing_fields,
         "invalid_fields": list(dict.fromkeys(invalid_fields)), "checks": total_checks},
        tuple(warnings),
    )
