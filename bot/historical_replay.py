"""Point-in-time historical replay through RNB's virtual execution path.

Market observations must be supplied from broker history. This module never
creates prices, fills missing bars, or admits data dated after a replay cycle.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Iterator

from bot.paper_executor import PaperExecutor
from bot.virtual_portfolio import VirtualPortfolio


@dataclass(frozen=True)
class HistoricalReplayCycle:
    timestamp: datetime
    scan: object
    eligible_buy_tickers: set[str] | None = None
    eligible_buy_reasons: dict[str, str] | None = None


@dataclass(frozen=True)
class HistoricalEquityPoint:
    timestamp: datetime
    equity: float | None
    cash: float
    protected_cash: float
    open_positions: int
    unpriced_tickers: tuple[str, ...]


@dataclass(frozen=True)
class HistoricalReplayResult:
    initial_balance: float
    final_equity: float | None
    total_return_pct: float | None
    total_trades: int
    buy_trades: int
    sell_trades: int
    realized_pnl: float
    commissions: float
    protected_cash: float
    max_drawdown: float | None
    max_drawdown_pct: float | None
    equity_curve: tuple[HistoricalEquityPoint, ...]
    warnings: tuple[str, ...]


class HistoricalReplay:
    """Replay chronological prepared scans against one virtual portfolio."""

    def __init__(self, portfolio: VirtualPortfolio, executor: PaperExecutor | None = None):
        self.portfolio = portfolio
        self.executor = executor or PaperExecutor()

    @staticmethod
    def _validate_cycles(
        cycles: Iterable[HistoricalReplayCycle],
    ) -> Iterator[HistoricalReplayCycle]:
        """Validate lazily so stateful cycle generators can observe each fill.

        Do not materialize this iterator: iter_historical_cycles deliberately
        pauses after yielding a scan and resumes only after its execution.
        """
        previous = None
        for index, cycle in enumerate(cycles):
            stamp = cycle.timestamp
            if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError(f"cycle {index} timestamp must be timezone-aware")
            if previous is not None and stamp <= previous:
                raise ValueError("historical cycles must be strictly chronological with unique timestamps")
            previous = stamp
            yield cycle

    def run(self, cycles: Iterable[HistoricalReplayCycle]) -> HistoricalReplayResult:
        curve = []
        warnings = set()
        for cycle in self._validate_cycles(cycles):
            self.executor.execute(
                self.portfolio,
                cycle.scan,
                eligible_buy_tickers=cycle.eligible_buy_tickers,
                eligible_buy_reasons=cycle.eligible_buy_reasons,
                as_of=cycle.timestamp,
            )
            prices = getattr(cycle.scan, "current_prices", {}) or {}
            equity, missing = self.portfolio.equity_with_available_prices(prices)
            if missing:
                warnings.add("incomplete_mark_to_market_due_to_missing_quotes")
            curve.append(HistoricalEquityPoint(
                timestamp=cycle.timestamp,
                equity=None if missing else equity,
                cash=float(self.portfolio.cash),
                protected_cash=float(self.portfolio.protected_cash),
                open_positions=len(self.portfolio.positions),
                unpriced_tickers=tuple(sorted(missing)),
            ))

        final_equity = curve[-1].equity if curve else None
        if final_equity is None:
            total_return = drawdown = drawdown_pct = None
            warnings.add("no_complete_final_equity")
        else:
            total_return = (final_equity / self.portfolio.initial_balance - 1.0) * 100.0
            peak = float(self.portfolio.initial_balance)
            drawdown = 0.0
            drawdown_pct = 0.0
            for point in curve:
                if point.equity is None:
                    continue
                peak = max(peak, point.equity)
                dd = peak - point.equity
                pct = dd / peak * 100.0 if peak else 0.0
                drawdown = max(drawdown, dd)
                drawdown_pct = max(drawdown_pct, pct)

        buys = [trade for trade in self.portfolio.trades if trade.side == "BUY"]
        sells = [trade for trade in self.portfolio.trades if trade.side == "SELL"]
        return HistoricalReplayResult(
            initial_balance=float(self.portfolio.initial_balance),
            final_equity=final_equity,
            total_return_pct=total_return,
            total_trades=len(self.portfolio.trades),
            buy_trades=len(buys),
            sell_trades=len(sells),
            realized_pnl=float(self.portfolio.realized_pnl),
            commissions=float(self.portfolio.commissions),
            protected_cash=float(self.portfolio.protected_cash),
            max_drawdown=drawdown,
            max_drawdown_pct=drawdown_pct,
            equity_curve=tuple(curve),
            warnings=tuple(sorted(warnings)),
        )


def iter_historical_cycles(
    candles_by_ticker: dict[str, list[object]],
    *,
    instrument_ids: dict[str, str],
    lot_sizes: dict[str, int],
    sessions_by_ticker: dict[str, dict],
    tradable_tickers: set[str],
    min_history: int = 20,
    momentum_period: int = 10,
    portfolio: VirtualPortfolio | None = None,
):
    """Build point-in-time scans and execute at the next bar's opening price.

    A cycle's strategy analysis sees only bars completed before that cycle.
    Current-cycle OHLC is used solely for the execution open, never as input to
    that cycle's signal. Missing opens are not replaced with closes or prior
    prices. Universe and instrument metadata remain caller-supplied point-in-time
    inputs; this function cannot reconstruct delisted/suspended historical names.
    """
    from bot.live_runner import LiveScanResult
    from bot.stock_analysis import StockAnalyzer
    from bot.intelligence.integration import analyze_scan
    from bot.intelligence.decision_engine import DecisionEngine

    if min_history < 2 or momentum_period <= 0 or momentum_period >= min_history:
        raise ValueError("invalid analyzer history configuration")
    if not candles_by_ticker:
        return []

    bars_by_time: dict[datetime, dict[str, object]] = {}
    for ticker, bars in candles_by_ticker.items():
        previous = None
        for bar in bars:
            stamp = getattr(bar, "time", None) or getattr(bar, "date", None)
            if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError(f"{ticker}: candle timestamp must be timezone-aware")
            if previous is not None and stamp <= previous:
                raise ValueError(f"{ticker}: candles must be strictly chronological")
            previous = stamp
            if ticker in bars_by_time.setdefault(stamp, {}):
                raise ValueError(f"{ticker}: duplicate candle timestamp")
            bars_by_time[stamp][ticker] = bar

    analyzer = StockAnalyzer(min_history=min_history, momentum_period=momentum_period)
    history: dict[str, list[object]] = {ticker: [] for ticker in candles_by_ticker}
    for stamp in sorted(bars_by_time):
        current_bars = bars_by_time[stamp]

        # Analyze only completed bars from before this execution timestamp.
        analyses, prices, previous_closes, visible_history, latest = {}, {}, {}, {}, {}
        for ticker, bar in current_bars.items():
            bars = history[ticker]
            if len(bars) < min_history:
                continue
            execution_open = _number(getattr(bar, "open", None))
            prior_close = _number(getattr(bars[-1], "close", None))
            if execution_open is None or prior_close is None or execution_open <= 0 or prior_close <= 0:
                continue
            try:
                result = analyzer.analyze(instrument_ids.get(ticker, ticker), ticker, bars)
            except (TypeError, ValueError, ArithmeticError):
                continue
            analyses[ticker] = result
            prices[ticker] = execution_open
            previous_closes[ticker] = prior_close
            visible_history[ticker] = list(bars)
            latest[ticker] = bars[-1]

        ranked = sorted(analyses.values(), key=lambda item: (
            -float(item.score), -float(item.momentum), float(item.volatility), item.ticker
        ))
        # Historical replay must not reuse today's exchange session as if it
        # were valid for an old candle. Require a broker-sourced schedule record
        # explicitly marked open for this exact Moscow calendar date.
        from zoneinfo import ZoneInfo
        moscow_date = stamp.astimezone(ZoneInfo("Europe/Moscow")).date().isoformat()
        buyable = {
            ticker for ticker in analyses
            if ticker in tradable_tickers
            and isinstance(lot_sizes.get(ticker), int)
            and not isinstance(lot_sizes.get(ticker), bool)
            and lot_sizes[ticker] > 0
            and _historical_session_is_open(sessions_by_ticker.get(ticker), moscow_date)
        }
        candidates = [item for item in ranked if item.ticker in buyable]
        scan = LiveScanResult(
            selected_10=ranked[:10],
            selected_3=candidates[:3],
            buy_candidates=candidates,
            analyses=analyses,
            current_prices=prices,
            previous_closes=previous_closes,
            lot_sizes={ticker: lot_sizes[ticker] for ticker in analyses if ticker in lot_sizes},
            active_trading_tickers=set(prices) & set(tradable_tickers),
            fresh_quote_tickers=set(prices),
            sellable_quote_tickers=set(prices),
            latest_candles=latest,
            candle_history=visible_history,
            session_by_ticker={ticker: sessions_by_ticker[ticker] for ticker in analyses if ticker in sessions_by_ticker},
        )
        # The generator pauses at each yield until HistoricalReplay has executed
        # the cycle. The next analysis therefore receives the updated portfolio.
        intelligence = analyze_scan(scan, portfolio=portfolio)
        decisions = DecisionEngine().evaluate(
            intelligence,
            held_tickers=set(portfolio.positions) if portfolio is not None else (),
        )
        approved = {
            ticker for ticker, decision in decisions.items()
            if decision.action == "BUY" and ticker in {item.ticker for item in candidates}
        }
        reasons = {ticker: decisions[ticker].reason for ticker in approved}
        yield HistoricalReplayCycle(stamp, scan, approved, reasons)

        # Only after decisions for this timestamp are formed does its candle
        # become available to the analyzer in the following cycle.
        for ticker, bar in current_bars.items():
            history[ticker].append(bar)
def build_historical_cycles(
    candles_by_ticker: dict[str, list[object]],
    *,
    instrument_ids: dict[str, str],
    lot_sizes: dict[str, int],
    sessions_by_ticker: dict[str, dict],
    tradable_tickers: set[str],
    min_history: int = 20,
    momentum_period: int = 10,
) -> list[HistoricalReplayCycle]:
    """Compatibility wrapper returning prepared cycles without portfolio context.

    Use iter_historical_cycles(..., portfolio=portfolio) with HistoricalReplay
    when portfolio-aware intelligence must observe each preceding execution.
    """
    return list(iter_historical_cycles(
        candles_by_ticker,
        instrument_ids=instrument_ids,
        lot_sizes=lot_sizes,
        sessions_by_ticker=sessions_by_ticker,
        tradable_tickers=tradable_tickers,
        min_history=min_history,
        momentum_period=momentum_period,
    ))


def _historical_session_is_open(session: object, expected_date: str) -> bool:
    """Accept only explicit, date-matched broker session evidence."""
    if not isinstance(session, dict):
        return False
    return (
        session.get("verified") is True
        and session.get("is_open") is True
        and session.get("schedule_date") == expected_date
        and bool(str(session.get("session") or "").strip())
        and bool(str(session.get("instrument_exchange") or "").strip())
    )


def _number(value: object) -> float | None:
    if value is None:
        return None
    units, nano = getattr(value, "units", None), getattr(value, "nano", None)
    try:
        number = float(units) + float(nano or 0) / 1_000_000_000 if units is not None else float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    import math
    return number if math.isfinite(number) else None
