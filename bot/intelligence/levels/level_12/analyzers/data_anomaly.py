from bot.intelligence.core.models.analysis_result import AnalyzerResult


def analyze(snapshot) -> AnalyzerResult:
    missing_fields = [
        name for name in (
            "previous_price", "volume", "average_volume", "volatility",
            "momentum", "liquidity",
        )
        if getattr(snapshot, name, None) is None
    ]
    invalid_fields = []
    if getattr(snapshot, "price", None) is None or snapshot.price <= 0:
        invalid_fields.append("price")
    if snapshot.previous_price is not None and snapshot.previous_price <= 0:
        invalid_fields.append("previous_price")
    if snapshot.volume is not None and snapshot.volume < 0:
        invalid_fields.append("volume")
    if snapshot.average_volume is not None and snapshot.average_volume <= 0:
        invalid_fields.append("average_volume")
    if snapshot.volatility is not None and snapshot.volatility < 0:
        invalid_fields.append("volatility")
    if snapshot.liquidity is not None and not 0.0 <= snapshot.liquidity <= 1.0:
        invalid_fields.append("liquidity")

    ohlc = {
        "open_price": snapshot.open_price,
        "high_price": snapshot.high_price,
        "low_price": snapshot.low_price,
        "close_price": snapshot.close_price,
    }
    supplied_ohlc = {name: value for name, value in ohlc.items() if value is not None}
    if supplied_ohlc and len(supplied_ohlc) != len(ohlc):
        invalid_fields.append("incomplete_ohlc")
    elif len(supplied_ohlc) == len(ohlc):
        if any(value <= 0 for value in supplied_ohlc.values()):
            invalid_fields.append("nonpositive_ohlc")
        elif (
            snapshot.low_price > min(snapshot.open_price, snapshot.close_price)
            or snapshot.high_price < max(snapshot.open_price, snapshot.close_price)
            or snapshot.low_price > snapshot.high_price
        ):
            invalid_fields.append("inconsistent_ohlc")

    total_checks = 6 + 1 + (1 if supplied_ohlc else 0)
    anomaly_count = len(missing_fields) + len(invalid_fields)
    score = min(1.0, anomaly_count / total_checks)
    confidence = max(0.0, 1.0 - len(missing_fields) / 6.0)
    warnings = []
    if missing_fields:
        warnings.append("market_snapshot_incomplete")
    if invalid_fields:
        warnings.append("market_snapshot_invalid_values")
    return AnalyzerResult(
        "data_anomaly", score, confidence,
        {"missing_fields": len(missing_fields), "missing_field_names": missing_fields,
         "invalid_fields": invalid_fields, "checks": total_checks},
        tuple(warnings),
    )
