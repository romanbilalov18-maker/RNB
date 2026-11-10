"""Point-in-time historical replay through RNB's virtual execution path.

Market observations must be supplied from broker history. This module never
creates prices, fills missing bars, or admits data dated after a replay cycle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from typing import Iterable, Iterator

from bot.paper_executor import PaperExecutor
from bot.virtual_portfolio import VirtualPortfolio


@dataclass(frozen=True)
class HistoricalReplayCycle:
    timestamp: datetime
    scan: object
    eligible_buy_tickers: set[str] | None = None
    eligible_buy_reasons: dict[str, str] | None = None
    decision_diagnostics: tuple[dict, ...] = ()


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
    decision_diagnostics: dict = field(default_factory=dict)


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
        decision_records = []
        for cycle in self._validate_cycles(cycles):
            decision_records.extend(cycle.decision_diagnostics or ())
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
            decision_diagnostics=_summarize_decision_diagnostics(decision_records),
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
    sectors_by_ticker: dict[str, str] | None = None,
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
    # Build feedback online from prior decisions only; never import live audit
    # data or release a label before three later broker sessions have closed.
    pending_learning: dict[str, list[dict]] = {ticker: [] for ticker in candles_by_ticker}
    learning_by_ticker: dict[str, list] = {ticker: [] for ticker in candles_by_ticker}
    for stamp in sorted(bars_by_time):
        current_bars = bars_by_time[stamp]

        # Mature feedback only from bars appended by earlier replay cycles.
        for ticker, pending_items in pending_learning.items():
            for item in list(pending_items):
                later = [
                    bar for bar in history[ticker]
                    if _historical_session_date(bar) > item["anchor_session_date"]
                ]
                if len(later) < 3:
                    continue
                target_price = _number(getattr(later[2], "close", None))
                anchor_price = item["anchor_price"]
                if target_price is None or target_price <= 0 or anchor_price <= 0:
                    pending_items.remove(item)
                    continue
                raw_return = target_price / anchor_price - 1.0
                cost_rate = 2.0 * float(getattr(portfolio, "commission_rate", 0.0005))
                net_return = raw_return - cost_rate
                action = item["recommendation"]
                outcome_return = net_return if action == "BUY" else -raw_return - cost_rate
                correct = net_return > 0 if action == "BUY" else raw_return < -cost_rate
                from bot.intelligence.levels.level_11.models.learning_observation import LearningObservation
                learning_by_ticker[ticker].append(LearningObservation(
                    outcome_return=outcome_return,
                    correct=bool(correct),
                    level_scores=item["level_scores"],
                    analyzer_scores=item["analyzer_scores"],
                    regime=item["regime"],
                    decision_time=item["decision_time"],
                    outcome_target_date=_historical_session_date(later[2]),
                ))
                pending_items.remove(item)
                learning_by_ticker[ticker] = learning_by_ticker[ticker][-200:]

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
        # A real T-Invest daily candle is evidence that the instrument had an
        # observed trading bar on this date. Do not project today's session
        # calendar backwards: it is not a historical exchange schedule.
        from zoneinfo import ZoneInfo
        moscow_date = stamp.astimezone(ZoneInfo("Europe/Moscow")).date().isoformat()
        cycle_sessions = {}
        for ticker in current_bars:
            base = sessions_by_ticker.get(ticker, {})
            exchange = str(base.get("instrument_exchange") or "").strip()
            if not exchange:
                continue
            cycle_sessions[ticker] = {
                "session": "daily_bar_observed",
                "instrument_exchange": exchange,
                "verified": True,
                "is_open": True,
                "schedule_date": moscow_date,
                "evidence": "T-Invest daily OHLCV candle exists for this ticker/date",
            }
        buyable = {
            ticker for ticker in analyses
            if ticker in tradable_tickers
            and isinstance(lot_sizes.get(ticker), int)
            and not isinstance(lot_sizes.get(ticker), bool)
            and lot_sizes[ticker] > 0
            and _historical_session_is_open(cycle_sessions.get(ticker), moscow_date)
        }
        candidates = [item for item in ranked if item.ticker in buyable]

        # Historical sector/market intelligence needs a same-cycle benchmark.
        # Build it only from observed next-bar opens and prior completed closes;
        # never substitute missing returns or use the current candle's close.
        import math
        observed_returns = []
        for ticker, current_price in prices.items():
            previous_price = previous_closes.get(ticker)
            if (
                isinstance(current_price, (int, float))
                and not isinstance(current_price, bool)
                and math.isfinite(current_price)
                and current_price > 0
                and isinstance(previous_price, (int, float))
                and not isinstance(previous_price, bool)
                and math.isfinite(previous_price)
                and previous_price > 0
            ):
                observed_returns.append(current_price / previous_price - 1.0)
        market_return = (
            sum(observed_returns) / len(observed_returns)
            if observed_returns else None
        )
        market_breadth = (
            sum(value > 0 for value in observed_returns) / len(observed_returns)
            if observed_returns else None
        )

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
            market_return=market_return,
            market_breadth=market_breadth,
            market_sample_count=len(observed_returns),
            sector_by_ticker={
                ticker: sector
                for ticker, sector in (sectors_by_ticker or {}).items()
                if isinstance(sector, str) and sector.strip()
            },
            session_by_ticker=cycle_sessions,
        )
        # The generator pauses at each yield until HistoricalReplay has executed
        # the cycle. The next analysis therefore receives the updated portfolio.
        observations = {
            ticker: tuple(items)
            for ticker, items in learning_by_ticker.items()
            if items
        }
        intelligence = analyze_scan(
            scan,
            learning_observations_by_ticker=observations,
            portfolio=portfolio,
        )
        decisions = DecisionEngine().evaluate(
            intelligence,
            held_tickers=set(portfolio.positions) if portfolio is not None else (),
        )
        approved = {
            ticker for ticker, decision in decisions.items()
            if decision.action == "BUY" and ticker in {item.ticker for item in candidates}
        }
        reasons = {ticker: decisions[ticker].reason for ticker in approved}
        # Preserve the exact decision-time L1-L15 snapshot and execution-open
        # anchor. Outcomes are admitted only after three later sessions close.
        from bot.decision_audit import DecisionAuditStore
        for ticker, decision in decisions.items():
            anchor = _number(prices.get(ticker))
            intelligence_item = intelligence.get(ticker)
            if decision.action not in {"BUY", "SELL"} or anchor is None or anchor <= 0 or intelligence_item is None:
                continue
            level_json, analyzer_json, regime = DecisionAuditStore._learning_snapshot(intelligence_item)
            pending_learning.setdefault(ticker, []).append({
                "anchor_price": anchor,
                "anchor_session_date": _historical_session_date(current_bars[ticker]) if ticker in current_bars else moscow_date,
                "recommendation": decision.action,
                "level_scores": json.loads(level_json),
                "analyzer_scores": json.loads(analyzer_json),
                "regime": regime,
                "decision_time": stamp.isoformat(),
            })
        candidate_tickers = {item.ticker for item in candidates}
        decision_diagnostics = tuple(
            {
                "ticker": ticker,
                "action": decisions[ticker].action,
                "reason": decisions[ticker].reason,
                "score": decisions[ticker].score,
                "confidence": decisions[ticker].confidence,
                "consistency": decisions[ticker].consistency,
                "confidence_breakdown": _confidence_breakdown(intelligence.get(ticker)),
            }
            if ticker in decisions else {
                "ticker": ticker,
                "action": "NO_INTELLIGENCE",
                "reason": "нет корректного результата Intelligence",
                "score": None,
                "confidence": None,
                "consistency": None,
                "confidence_breakdown": {},
            }
            for ticker in sorted(candidate_tickers)
        )
        yield HistoricalReplayCycle(stamp, scan, approved, reasons, decision_diagnostics)

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
    sectors_by_ticker: dict[str, str] | None = None,
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
        sectors_by_ticker=sectors_by_ticker,
    ))


def _historical_session_date(candle: object) -> str:
    """Return a broker candle's Moscow session date; reject missing timestamps."""
    from zoneinfo import ZoneInfo

    stamp = getattr(candle, "time", None) or getattr(candle, "date", None)
    if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("historical learning candle timestamp must be timezone-aware")
    return stamp.astimezone(ZoneInfo("Europe/Moscow")).date().isoformat()



def _confidence_breakdown(intelligence: object) -> dict:
    """Expose per-level and per-analyzer confidence without changing decisions."""
    if intelligence is None:
        return {}
    breakdown = {}
    for level in range(1, 16):
        prefix = f"L{level:02d}"
        result = getattr(intelligence, f"level_{level:02d}", None)
        confidence = getattr(result, "confidence", None)
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
            breakdown[prefix] = float(confidence)

        analyzer_results = getattr(result, "analyzer_results", None)
        if isinstance(analyzer_results, dict):
            items = analyzer_results.items()
        else:
            items = (
                (getattr(item, "analyzer", None), item)
                for item in (analyzer_results or ())
            )
        for name, analyzer_result in items:
            analyzer_confidence = getattr(analyzer_result, "confidence", None)
            if (
                isinstance(name, str) and name
                and isinstance(analyzer_confidence, (int, float))
                and not isinstance(analyzer_confidence, bool)
            ):
                breakdown[f"{prefix}.{name}"] = float(analyzer_confidence)
    return breakdown


def _summarize_decision_diagnostics(records: list[dict]) -> dict:
    """Aggregate candidate decisions without changing authorization thresholds."""
    from collections import Counter

    actions = Counter()
    reasons = Counter()
    metrics = {name: [] for name in ("score", "confidence", "consistency")}
    for record in records:
        actions[str(record.get("action") or "UNKNOWN")] += 1
        reasons[str(record.get("reason") or "unknown")] += 1
        for name in metrics:
            value = record.get(name)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                import math
                if math.isfinite(float(value)):
                    metrics[name].append(float(value))

    confidence_breakdown_values = {}
    for record in records:
        for name, value in (record.get("confidence_breakdown") or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                import math
                if math.isfinite(float(value)):
                    confidence_breakdown_values.setdefault(name, []).append(float(value))

    confidence_breakdown_summary = {
        name: {
            "observations": len(values),
            "minimum": min(values),
            "maximum": max(values),
            "mean": sum(values) / len(values),
        }
        for name, values in sorted(confidence_breakdown_values.items())
        if values
    }

    metric_summary = {}
    for name, values in metrics.items():
        metric_summary[name] = {
            "observations": len(values),
            "minimum": min(values) if values else None,
            "maximum": max(values) if values else None,
            "mean": sum(values) / len(values) if values else None,
        }
    return {
        "candidate_decisions": len(records),
        "action_counts": dict(sorted(actions.items())),
        "reason_counts": dict(sorted(reasons.items())),
        "metric_summary": metric_summary,
        "confidence_breakdown_summary": confidence_breakdown_summary,
        "authorization_thresholds": {
            "minimum_buy_score": 0.60,
            "minimum_confidence": 0.50,
            "minimum_consistency": 0.50,
            "thresholds_changed": False,
        },
    }


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
