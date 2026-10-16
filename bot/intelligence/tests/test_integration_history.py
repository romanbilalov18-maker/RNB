from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bot.intelligence.integration import _returns_by_date, build_market_snapshot


def _candle(day, close, volume=100):
    return SimpleNamespace(
        time=datetime(2026, 10, day, tzinfo=timezone.utc),
        close=close,
        open=close,
        high=close,
        low=close,
        volume=volume,
    )


def _scan(candles):
    return SimpleNamespace(
        current_prices={"AAA": 12.0, "BBB": 20.0},
        previous_closes={"AAA": 11.0, "BBB": 19.0},
        latest_candles={"AAA": _candle(3, 12.0)},
        candle_history={"AAA": candles, "BBB": [_candle(1, 18.0), _candle(2, 19.0)]},
        sector_by_ticker={"AAA": "technology", "BBB": "technology"},
        lot_sizes={"AAA": 1},
        market_return=None,
        market_breadth=None,
        market_sample_count=0,
    )


def test_returns_by_date_rejects_duplicate_candle_timestamps():
    candles = [_candle(1, 10.0), _candle(2, 11.0), _candle(2, 12.0), _candle(3, 13.0)]

    assert _returns_by_date(candles) == {}


def test_returns_by_date_preserves_clean_real_observations():
    candles = [_candle(1, 10.0), _candle(2, 11.0), _candle(3, 12.1)]

    returns = _returns_by_date(candles)

    assert returns == {
        datetime(2026, 10, 2, tzinfo=timezone.utc).isoformat(): 0.1,
        datetime(2026, 10, 3, tzinfo=timezone.utc).isoformat(): 0.1,
    }


def test_snapshot_does_not_pass_ambiguous_history_to_level_09():
    candles = [_candle(1, 10.0), _candle(2, 11.0), _candle(2, 12.0), _candle(3, 13.0)]
    analysis = SimpleNamespace(
        ticker="AAA",
        average_volume=100.0,
        volatility=0.1,
        momentum=0.02,
    )
    position = SimpleNamespace(quantity=2, average_price=9.0)
    portfolio = SimpleNamespace(positions={"AAA": position, "BBB": SimpleNamespace(quantity=1, average_price=18.0)})

    snapshot = build_market_snapshot(_scan(candles), analysis, portfolio=portfolio)

    assert snapshot is not None
    assert snapshot.portfolio_context_available is True
    assert snapshot.price == 12.0
    assert len(snapshot.portfolio_positions) == 2
    held = {item["symbol"]: item for item in snapshot.portfolio_positions}
    assert held["AAA"]["market_value"] == 24.0
    assert held["AAA"]["market_value_available"] is True
    assert held["AAA"]["historical_return_dates"] == []
    assert held["AAA"]["historical_returns"] == []
    assert snapshot.historical_returns == ()
