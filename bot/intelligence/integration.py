from __future__ import annotations

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.pipeline.intelligence_pipeline import IntelligencePipeline


def _quotation(value: object) -> float:
    units = getattr(value, "units", None)
    nano = getattr(value, "nano", None)
    if units is None:
        return float(value)
    return float(units) + float(nano or 0) / 1_000_000_000


def build_market_snapshot(scan, analysis) -> MarketSnapshot | None:
    """Build Intelligence input from the current real-market scan."""
    ticker = analysis.ticker
    price = scan.current_prices.get(ticker)
    previous_close = scan.previous_closes.get(ticker)
    if price is None or previous_close is None or price <= 0 or previous_close <= 0:
        return None

    candle = scan.latest_candles.get(ticker)
    open_price = high_price = low_price = close_price = None
    candle_volume = candle_range = close_position = volume_ratio = None

    if candle is not None:
        values = [getattr(candle, name, None) for name in ("open", "high", "low", "close")]
        if all(value is not None for value in values):
            open_price, high_price, low_price, close_price = (
                _quotation(value) for value in values
            )
            candle_volume = float(getattr(candle, "volume", 0) or 0)
            if close_price > 0 and high_price >= low_price:
                candle_range = (high_price - low_price) / close_price
            if high_price > low_price:
                close_position = (close_price - low_price) / (high_price - low_price)
            if analysis.average_volume > 0:
                volume_ratio = candle_volume / analysis.average_volume

    return MarketSnapshot(
        symbol=ticker,
        price=float(price),
        previous_price=float(previous_close),
        volume=candle_volume,
        average_volume=float(analysis.average_volume),
        volatility=float(analysis.volatility),
        momentum=float(analysis.momentum),
        liquidity=min(max(float(analysis.volume_ratio) / 2.0, 0.0), 1.0),
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        candle_volume=candle_volume,
        average_candle_volume=float(analysis.average_volume),
        candle_range=candle_range,
        close_position=close_position,
        volume_ratio=volume_ratio,
        lot_size=scan.lot_sizes.get(ticker, 1),
    )


def analyze_scan(scan, pipeline=None) -> dict:
    """Run L1-L15 for scanned candidates and holdings; never executes trades."""
    pipeline = pipeline or IntelligencePipeline()
    analyses = dict(scan.analyses)
    for analysis in scan.buy_candidates:
        analyses.setdefault(analysis.ticker, analysis)

    results = {}
    for ticker, analysis in analyses.items():
        snapshot = build_market_snapshot(scan, analysis)
        if snapshot is not None:
            results[ticker] = pipeline.analyze(snapshot)
    return results
