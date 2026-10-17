from __future__ import annotations

from bot.intelligence.core.models.market_snapshot import MarketSnapshot
from bot.intelligence.pipeline.intelligence_pipeline import IntelligencePipeline


def _quotation(value: object) -> float:
    units = getattr(value, "units", None)
    nano = getattr(value, "nano", None)
    if units is None:
        return float(value)
    return float(units) + float(nano or 0) / 1_000_000_000


def _close(value: object) -> float | None:
    raw = getattr(value, "close", None)
    if raw is None:
        return None
    try:
        result = _quotation(raw)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _candle_date(candle: object) -> str | None:
    value = getattr(candle, "time", None) or getattr(candle, "date", None)
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _history_warnings(candles, *, candidate: bool = False) -> tuple[str, ...]:
    """Describe known history defects without inventing or repairing observations."""
    seen_dates = set()
    duplicate_dates = set()
    for candle in candles or ():
        day = _candle_date(candle)
        if day is None or _close(candle) is None:
            continue
        if day in seen_dates:
            duplicate_dates.add(day)
        seen_dates.add(day)
    if duplicate_dates:
        warning = (
            "portfolio_candidate_history_duplicate_timestamps"
            if candidate else "portfolio_position_history_duplicate_timestamps"
        )
        return (warning,)
    return ()


def _returns_by_date(candles) -> dict[str, float]:
    points = []
    seen_dates = set()
    duplicate_dates = set()
    for candle in candles or ():
        close = _close(candle)
        day = _candle_date(candle)
        if close is not None and day is not None:
            if day in seen_dates:
                duplicate_dates.add(day)
            seen_dates.add(day)
            points.append((day, close))
    # A duplicate timestamp makes the return for that interval ambiguous.
    # Do not select an arbitrary close or let a later item overwrite a return.
    if duplicate_dates:
        return {}
    points.sort()
    result = {}
    for (previous_day, previous), (day, current) in zip(points, points[1:]):
        if previous > 0 and current > 0 and day != previous_day:
            result[day] = current / previous - 1.0
    return result


def _aligned_peer_series(
    scan,
    ticker: str,
    target_returns: dict[str, float],
    sector: str | None = None,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    peer_series = []
    for peer, candles in getattr(scan, "candle_history", {}).items():
        if peer == ticker:
            continue
        if sector is not None and getattr(scan, "sector_by_ticker", {}).get(peer) != sector:
            continue
        values = _returns_by_date(candles)
        if values:
            peer_series.append(values)
    aligned_target = []
    aligned_peers = []
    for day in sorted(target_returns):
        observations = [values[day] for values in peer_series if day in values]
        if observations:
            aligned_target.append(target_returns[day])
            aligned_peers.append(sum(observations) / len(observations))
    return tuple(aligned_target), tuple(aligned_peers)


def build_market_snapshot(scan, analysis, portfolio=None) -> MarketSnapshot | None:
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

    own_candles = getattr(scan, "candle_history", {}).get(ticker, ())
    own_returns = _returns_by_date(own_candles)
    own_history_warnings = _history_warnings(own_candles, candidate=True)
    sector = getattr(scan, "sector_by_ticker", {}).get(ticker)
    _, sector_history = _aligned_peer_series(scan, ticker, own_returns, sector) if sector else ((), ())
    correlation_asset_returns, market_history = _aligned_peer_series(scan, ticker, own_returns)
    sector_changes = [
        current / previous - 1.0
        for peer, current in scan.current_prices.items()
        if peer != ticker and sector
        and getattr(scan, "sector_by_ticker", {}).get(peer) == sector
        and (previous := scan.previous_closes.get(peer)) is not None
        and previous > 0 and current > 0
    ]
    # Exclude the analyzed instrument from its sector benchmark. Otherwise its
    # own return leaks into the comparison and weakens/changes the relative signal.
    peer_return = sum(sector_changes) / len(sector_changes) if sector_changes else None
    leave_one_out_changes = [
        current / previous - 1.0
        for peer, current in scan.current_prices.items()
        if peer != ticker
        and (previous := scan.previous_closes.get(peer)) is not None
        and previous > 0 and current > 0
    ]
    relative_market_return = (
        sum(leave_one_out_changes) / len(leave_one_out_changes)
        if leave_one_out_changes else None
    )
    # The aggregate sector return includes the target instrument and cannot be
    # used as a fallback without its sample count and a leave-one-out adjustment.
    # Unknown peer data must remain unknown rather than leak the target return.
    sector_return = peer_return
    history_volumes = [
        float(getattr(item, "volume", 0) or 0)
        for item in getattr(scan, "candle_history", {}).get(ticker, ())
        if float(getattr(item, "volume", 0) or 0) > 0
    ]
    average_history_volume = sum(history_volumes) / len(history_volumes) if history_volumes else 0.0
    volume_ratios = tuple(value / average_history_volume for value in history_volumes[1:]) if average_history_volume > 0 else ()
    positions = []
    for symbol, position in getattr(portfolio, "positions", {}).items():
        market_price = scan.current_prices.get(symbol)
        position_candles = getattr(scan, "candle_history", {}).get(symbol, ())
        position_returns = _returns_by_date(position_candles)
        positions.append({
            "symbol": symbol,
            "quantity": int(getattr(position, "quantity", 0)),
            "average_price": float(getattr(position, "average_price", 0.0)),
            "market_value": float(market_price or 0.0) * int(getattr(position, "quantity", 0)),
            "market_value_available": market_price is not None and float(market_price) > 0,
            "sector": getattr(scan, "sector_by_ticker", {}).get(symbol),
            "historical_return_dates": list(sorted(position_returns)),
            "historical_returns": [value for _, value in sorted(position_returns.items())],
            "historical_return_warnings": list(_history_warnings(position_candles)),
        })

    return MarketSnapshot(
        symbol=ticker,
        price=float(price),
        previous_price=float(previous_close),
        volume=candle_volume,
        average_volume=float(analysis.average_volume),
        volatility=float(analysis.volatility),
        momentum=float(analysis.momentum),
        # Volume ratio is not a liquidity measurement. Keep liquidity unknown
        # until the source supplies a real metric (e.g. spread/depth).
        liquidity=None,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        candle_volume=candle_volume,
        average_candle_volume=float(analysis.average_volume),
        candle_range=candle_range,
        close_position=close_position,
        volume_ratio=volume_ratio,
        lot_size=scan.lot_sizes.get(ticker),
        market_return=getattr(scan, "market_return", None),
        market_breadth=getattr(scan, "market_breadth", None),
        market_sample_count=getattr(scan, "market_sample_count", 0),
        relative_market_return=relative_market_return,
        relative_market_sample_count=len(leave_one_out_changes),
        relative_market_context_available=bool(leave_one_out_changes),
        sector=sector,
        sector_return=sector_return,
        peer_return=peer_return,
        peer_count=len(sector_changes),
        historical_returns=tuple(own_returns[day] for day in sorted(own_returns)),
        historical_return_dates=tuple(sorted(own_returns)),
        historical_return_warnings=own_history_warnings,
        market_return_history=market_history,
        correlation_asset_returns=correlation_asset_returns,
        correlation_benchmark="scanned_peer_basket" if market_history else None,
        sector_return_history=sector_history,
        peer_return_history=sector_history,
        historical_volume_ratios=volume_ratios,
        portfolio_positions=tuple(positions),
        portfolio_context_available=portfolio is not None,
    )


def analyze_scan(scan, pipeline=None, learning_observations_by_ticker=None, portfolio=None) -> dict:
    """Run L1-L15 for scanned candidates and holdings; never executes trades."""
    analyses = dict(scan.analyses)
    for analysis in scan.buy_candidates:
        analyses.setdefault(analysis.ticker, analysis)

    observations_by_ticker = learning_observations_by_ticker or {}
    results = {}
    for ticker, analysis in analyses.items():
        snapshot = build_market_snapshot(scan, analysis, portfolio=portfolio)
        if snapshot is None:
            continue
        # A supplied test/custom pipeline keeps its existing behavior. The live
        # path creates a per-ticker pipeline so L11 only learns from that ticker's
        # matured historical outcomes.
        active_pipeline = pipeline or IntelligencePipeline(
            learning_observations=tuple(observations_by_ticker.get(ticker, ()))
        )
        results[ticker] = active_pipeline.analyze(snapshot)
    return results
