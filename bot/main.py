from __future__ import annotations

import math
import os
import time
from collections import Counter

from bot.config import Config
from bot.decision_audit import DecisionAuditStore
from bot.intelligence.decision_engine import DecisionEngine
from bot.intelligence.integration import analyze_scan
from bot.live_runner import LiveMarketRunner
from bot.paper_executor import PaperExecutor
from bot.position_health import assess_position_health
from bot.portfolio_store import SQLitePortfolioStore


def _should_run_another_cycle(remaining_seconds: float, cycle_interval_minutes: float) -> bool:
    """Only start another cycle when more than one full interval remains."""
    return remaining_seconds > cycle_interval_minutes * 60


def _authorized_buys(decisions, missing_held_prices):
    """Fail closed on new entries whenever any open holding lacks a fresh quote."""
    if missing_held_prices:
        missing = ", ".join(sorted(missing_held_prices))
        print(
            "NEW ENTRIES BLOCKED: portfolio valuation is incomplete because "
            f"open holdings have no verified fresh quote: {missing}"
        )
        return set(), {}
    eligible = {
        ticker: decision
        for ticker, decision in decisions.items()
        if getattr(decision, "action", None) == "BUY"
    }
    return set(eligible), {
        ticker: decision.reason for ticker, decision in eligible.items()
    }


def main() -> None:
    config = Config.from_env()
    run_duration_minutes = _env_positive_float("RUN_DURATION_MINUTES", 60.0)
    cycle_interval_minutes = _env_positive_float("CYCLE_INTERVAL_MINUTES", 5.0)
    if cycle_interval_minutes > run_duration_minutes:
        raise ValueError("CYCLE_INTERVAL_MINUTES must not exceed RUN_DURATION_MINUTES")

    store = SQLitePortfolioStore(config.portfolio_db_path)
    audit_store = DecisionAuditStore(
        os.getenv("DECISION_AUDIT_DB", "data/decision_audit.sqlite")
    )
    portfolio = store.load_or_create(
        initial_balance=config.initial_virtual_balance,
        commission_rate=config.commission_rate,
    )
    _reconcile_cycle_history(store, audit_store)

    # Snapshot run-level counters so the final report separates this invocation
    # from the cumulative portfolio history restored from SQLite.
    run_started_monotonic = time.monotonic()
    starting_trade_count = len(portfolio.trades)
    starting_realized_pnl = portfolio.realized_pnl
    starting_commissions = portfolio.commissions
    starting_reserve = portfolio.protected_cash
    last_report_result = None
    last_intelligence_results = {}
    last_decisions = {}

    deadline = run_started_monotonic + run_duration_minutes * 60
    cycle = 0

    # Import the broker SDK only for an actual live run. Unit tests can import
    # this module without network access to the official SDK package index.
    from t_tech.invest import Client

    with Client(config.invest_token) as client:
        # Reuse the runner so its official exchange-schedule cache survives cycles.
        market_runner = LiveMarketRunner(client)
        while True:
            if cycle and not _should_run_another_cycle(
                deadline - time.monotonic(), cycle_interval_minutes
            ):
                print(f"Runtime limit reached before cycle {cycle + 1}.")
                break

            cycle += 1
            print()
            print(f"=== CYCLE {cycle} ===")
            print(f"Runtime limit: {run_duration_minutes:g} min")
            print(f"Cycle interval: {cycle_interval_minutes:g} min")
            print(f"Take Profit: {config.take_profit_percent:g} %")

            try:
                result = market_runner.run(
                    held_tickers=set(portfolio.positions),
                    tracked_tickers=audit_store.pending_tickers(),
                )
                active_tickers = getattr(result, "active_trading_tickers", None)
                # Do not label a closed-session snapshot as a current valuation.
                last_report_result = result if active_tickers is None or bool(active_tickers) else None
                if active_tickers is not None and not active_tickers:
                    print(
                        "No active T-Invest trading session. Virtual trades and decision "
                        "anchors are disabled; collecting completed historical candles only."
                    )
                    collection = audit_store.record_market_session_prices(
                        result.candle_history,
                        commission_rate=portfolio.commission_rate,
                    )
                    learning_count = sum(
                        len(items)
                        for items in audit_store.learning_observations_by_ticker().values()
                    )
                    print(
                        "L11 closed-session collection: "
                        f"prices_added={collection['prices_added']} "
                        f"prices_updated={collection['prices_updated']} "
                        f"outcomes_newly_evaluated={collection['outcomes_added']} "
                        f"learning_observations_ready={learning_count}"
                    )
                    remaining = deadline - time.monotonic()
                    if not _should_run_another_cycle(remaining, cycle_interval_minutes):
                        print("Runtime limit reached while market session is inactive.")
                        break
                    time.sleep(cycle_interval_minutes * 60)
                    continue
                _, missing_held_prices = portfolio.equity_with_available_prices(
                    result.current_prices
                )
                if missing_held_prices:
                    print(
                        "PORTFOLIO VALUATION INCOMPLETE: positions without verified "
                        "fresh quotes will be held and excluded from market valuation: "
                        + ", ".join(missing_held_prices)
                    )
                learning_observations = audit_store.learning_observations_by_ticker()
                intelligence_results = analyze_scan(
                    result,
                    learning_observations_by_ticker=learning_observations,
                    portfolio=portfolio,
                )
                intelligence_results = _filter_intelligence_to_active_tickers(
                    intelligence_results,
                    active_tickers,
                )
                decision_engine = DecisionEngine()
                decisions = decision_engine.evaluate(
                    intelligence_results,
                    held_tickers=set(portfolio.positions),
                )
                last_intelligence_results = intelligence_results
                last_decisions = decisions
                _print_decision_diagnostics(decisions, decision_engine)
                # Only explicit BUY recommendations from a valid L1-L15 result may
                # authorize new virtual entries. Existing PositionManager exits and
                # PositionSizer risk/cash/commission controls remain authoritative.
                eligible_buy_tickers, eligible_buy_reasons = _authorized_buys(
                    decisions, missing_held_prices
                )
                reserve_before_cycle = portfolio.protected_cash
                sell_trades, buy_trades = PaperExecutor(
                    take_profit=config.take_profit_percent / 100.0
                ).execute(
                    portfolio,
                    result,
                    eligible_buy_tickers=eligible_buy_tickers,
                    eligible_buy_reasons=eligible_buy_reasons,
                )

                equity, missing_held_prices = portfolio.equity_with_available_prices(
                    result.current_prices
                )
                equity_complete = not missing_held_prices
                if not equity_complete:
                    print(
                        "PORTFOLIO EQUITY STATUS: PARTIAL (not a complete mark-to-market "
                        f"value); unpriced_positions={','.join(missing_held_prices)}"
                    )
                cycle_id = f"{cycle}:{time.time_ns()}"
                audit_count = _persist_cycle_safely(
                    store,
                    audit_store,
                    portfolio,
                    result.current_prices,
                    cycle_id=cycle_id,
                    decisions=decisions,
                    virtual_trades=[*sell_trades, *buy_trades],
                    equity=equity,
                    equity_complete=equity_complete,
                    cash=portfolio.cash,
                    total_commissions=portfolio.commissions,
                    current_prices=result.current_prices,
                    candle_history=result.candle_history,
                    intelligence_results=intelligence_results,
                    commission_rate=portfolio.commission_rate,
                )
                print(f"Decision audit: recorded {audit_count} ticker observations")
                print(f"Decision audit summary: {audit_store.summary()}")
                history = store.equity_history()
                stats = portfolio.statistics(equity, history)

                _print_cycle_result(
                    portfolio,
                    result,
                    sell_trades,
                    buy_trades,
                    equity,
                    stats,
                    config.take_profit_percent,
                    intelligence_results,
                    decisions,
                    equity_complete=equity_complete,
                    reserve_added_this_cycle=portfolio.protected_cash - reserve_before_cycle,
                )

            except CycleConsistencyError as exc:
                # The in-memory portfolio may contain mutations that were not durably
                # committed. Never print those as the final account state.
                print(
                    f"FATAL: {type(exc).__name__}: {exc} "
                    "Stopping bot to prevent further inconsistent cycles."
                )
                try:
                    portfolio = store.load_or_create(
                        initial_balance=config.initial_virtual_balance,
                        commission_rate=config.commission_rate,
                    )
                except Exception as restore_error:
                    print(
                        "FATAL: unable to restore the last durable virtual portfolio; "
                        f"{type(restore_error).__name__}: {restore_error}. "
                        "No final balance report will be produced because state is unverified."
                    )
                    return
                break
            except Exception as exc:
                print(f"Cycle {cycle} failed: {type(exc).__name__}: {exc}")
                # Discard any uncommitted in-memory mutations and resume from
                # the last durable portfolio snapshot before the next attempt.
                portfolio = store.load_or_create(
                    initial_balance=config.initial_virtual_balance,
                    commission_rate=config.commission_rate,
                )
                remaining_after_error = deadline - time.monotonic()
                if not _should_run_another_cycle(remaining_after_error, cycle_interval_minutes):
                    print("Runtime limit reached after failed cycle; stopping safely.")
                    break
                print(f"Retrying in {cycle_interval_minutes:.2f} min from saved portfolio state.")
                time.sleep(cycle_interval_minutes * 60)
                continue

            remaining = deadline - time.monotonic()
            if not _should_run_another_cycle(remaining, cycle_interval_minutes):
                print(f"Runtime limit reached after cycle {cycle}.")
                break

            sleep_seconds = cycle_interval_minutes * 60
            print(f"Next cycle in {sleep_seconds / 60:.2f} min.")
            time.sleep(sleep_seconds)

    _print_end_of_run_report(
        portfolio=portfolio,
        starting_trade_count=starting_trade_count,
        starting_realized_pnl=starting_realized_pnl,
        starting_commissions=starting_commissions,
        starting_reserve=starting_reserve,
        elapsed_minutes=(time.monotonic() - run_started_monotonic) / 60.0,
        cycles_started=cycle,
        last_result=last_report_result,
        intelligence_results=last_intelligence_results,
        decisions=last_decisions,
    )


def _print_end_of_run_report(
    *,
    portfolio,
    starting_trade_count: int,
    starting_realized_pnl: float,
    starting_commissions: float,
    starting_reserve: float,
    elapsed_minutes: float,
    cycles_started: int,
    last_result,
    intelligence_results=None,
    decisions=None,
) -> None:
    """Print run-scoped trade totals and portfolio value without inventing prices."""
    run_trades = portfolio.trades[starting_trade_count:]
    run_buys = [trade for trade in run_trades if trade.side == "BUY"]
    run_sells = [trade for trade in run_trades if trade.side == "SELL"]
    report_prices = getattr(last_result, "current_prices", {}) or {}
    final_equity, missing_final_prices = portfolio.equity_with_available_prices(report_prices)
    print()
    print("=" * 20 + " RNB — ИТОГ ВСЕГО ЗАПУСКА " + "=" * 20)
    print(f"Длительность: {elapsed_minutes:.2f} мин; циклов начато: {cycles_started}.")
    print(f"Сделок за этот запуск: {len(run_trades)} (покупок={len(run_buys)}, продаж={len(run_sells)}).")
    print(f"Реализованный P/L за запуск: {portfolio.realized_pnl - starting_realized_pnl:+.2f} RUB.")
    print(f"Комиссии за запуск: {portfolio.commissions - starting_commissions:.2f} RUB.")
    print(f"Изменение защищённого резерва за запуск: {portfolio.protected_cash - starting_reserve:.2f} RUB.")
    print("Оценка позиций использует последний подтверждённый снимок активной торговой сессии; новый запрос после остановки не выполняется.")
    if missing_final_prices:
        print("Итоговая оценка неполная; позиции без свежих цен: " + ", ".join(missing_final_prices))
    _print_readable_cycle_summary(
        portfolio=portfolio,
        result=last_result,
        sell_trades=run_sells,
        buy_trades=run_buys,
        equity=final_equity,
        equity_complete=not missing_final_prices,
        intelligence_results=intelligence_results,
        decisions=decisions,
        reserve_added_this_cycle=portfolio.protected_cash - starting_reserve,
        scope_label="Весь запуск",
    )


def _validate_held_position_prices(portfolio, market_prices) -> None:
    """Reject stale/missing quote snapshots before mutating the portfolio."""
    missing = sorted(set(portfolio.positions) - set(market_prices))
    if missing:
        raise RuntimeError(
            "Cycle skipped: no verified fresh T-Invest prices for open positions: "
            + ", ".join(missing)
            + ". Portfolio was not changed; inspect T-Invest provenance diagnostics."
        )


class CycleConsistencyError(RuntimeError):
    """Raised when audit and portfolio persistence cannot be reconciled safely."""


def _reconcile_cycle_history(portfolio_store, audit_store) -> None:
    """Reconcile audit rows against cycle IDs committed with the portfolio."""
    audit_ids = audit_store.cycle_ids()
    if not portfolio_store.cycle_tracking_initialized():
        # One-time baseline for databases created before cycle markers existed.
        portfolio_store.seed_legacy_committed_cycles(audit_ids)

    committed_ids = portfolio_store.committed_cycle_ids()
    missing_audit = committed_ids - audit_ids
    if missing_audit:
        raise CycleConsistencyError(
            "Committed portfolio cycle(s) are missing from decision audit: "
            + ", ".join(sorted(missing_audit))
            + "; refusing to start with inconsistent history."
        )

    for cycle_id in sorted(audit_ids - committed_ids):
        audit_store.delete_cycle(cycle_id)


def _persist_cycle_safely(
    portfolio_store,
    audit_store,
    portfolio,
    market_prices,
    *,
    cycle_id: str,
    **audit_kwargs,
) -> int:
    """Persist a cycle once; reject ambiguous prior writes instead of replaying it."""
    committed_lookup = getattr(type(portfolio_store), "committed_cycle_ids", None)
    audit_lookup = getattr(type(audit_store), "cycle_ids", None)
    if callable(committed_lookup) and callable(audit_lookup):
        committed_ids = committed_lookup(portfolio_store)
        audit_ids = audit_lookup(audit_store)
        if cycle_id in committed_ids:
            if cycle_id not in audit_ids:
                raise CycleConsistencyError(
                    f"Cycle {cycle_id} is committed in the portfolio but missing from audit."
                )
            count_cycle = getattr(type(audit_store), "cycle_record_count", None)
            return count_cycle(audit_store, cycle_id) if callable(count_cycle) else 0
        if cycle_id in audit_ids:
            raise CycleConsistencyError(
                f"Cycle {cycle_id} already exists in audit but is not committed in the portfolio; "
                "run startup reconciliation before retrying."
            )

    audit_count = _record_cycle_with_retries(
        audit_store, cycle_id=cycle_id, **audit_kwargs
    )
    try:
        portfolio_store.save(portfolio, market_prices, cycle_id=cycle_id)
    except Exception as save_error:
        try:
            audit_store.delete_cycle(cycle_id)
        except Exception as rollback_error:
            raise CycleConsistencyError(
                "Portfolio save failed and audit rollback also failed; "
                f"manual reconciliation is required for cycle {cycle_id}."
            ) from rollback_error
        raise save_error
    return audit_count


def _record_cycle_with_retries(audit_store, *, cycle_id: str, **kwargs) -> int:
    """Retry transient audit persistence failures with a stable idempotency key."""
    last_error = None
    for attempt in range(1, 4):
        try:
            return audit_store.record_cycle(cycle_id=cycle_id, **kwargs)
        except Exception as exc:
            last_error = exc
            print(
                f"Decision audit write attempt {attempt}/3 failed: "
                f"{type(exc).__name__}: {exc}"
            )
            if attempt < 3:
                time.sleep(2 ** (attempt - 1))
    raise RuntimeError("Decision audit write failed after 3 attempts") from last_error

def _env_positive_float(name: str, default: float) -> float:
    """Read a positive, finite float from the environment.

    NaN and infinities must be rejected explicitly because ordinary
    comparisons do not reliably reject non-finite values.
    """
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a positive finite number") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return value



def _filter_intelligence_to_active_tickers(intelligence_results, active_tickers):
    """Keep DecisionEngine inputs limited to schedule/status/fresh-quote eligible tickers.

    A None allowlist preserves legacy/test behavior; an empty set intentionally
    excludes every ticker and produces no DecisionEngine recommendations.
    """
    if active_tickers is None:
        return dict(intelligence_results)
    allowed = set(active_tickers)
    return {
        ticker: intelligence
        for ticker, intelligence in intelligence_results.items()
        if ticker in allowed
    }


def _print_decision_diagnostics(decisions, engine: DecisionEngine) -> None:
    """Print a complete per-cycle decision summary without changing trade rules."""
    action_counts = Counter(decision.action for decision in decisions.values())
    reason_counts = Counter(decision.reason for decision in decisions.values())
    print(
        "DECISION GATE THRESHOLDS: "
        f"BUY score>={engine.min_buy_score:.2f}, "
        f"confidence>={engine.min_confidence:.2f}, "
        f"consistency>={engine.min_consistency:.2f}; "
        f"held-position SELL score<={engine.max_sell_score:.2f}, "
        f"confidence>={engine.min_sell_confidence:.2f}"
    )
    print(
        "DECISION SUMMARY: "
        f"total={len(decisions)} "
        f"BUY={action_counts.get('BUY', 0)} "
        f"WAIT={action_counts.get('WAIT', 0)} "
        f"HOLD={action_counts.get('HOLD', 0)} "
        f"SELL={action_counts.get('SELL', 0)}"
    )
    if reason_counts:
        print("DECISION REASONS: " + "; ".join(
            f"{reason}={count}"
            for reason, count in sorted(reason_counts.items())
        ))
    else:
        print("DECISION REASONS: no decisions")


def _format_selected_analysis_line(analysis, current_prices, lot_sizes) -> str:
    """Format a selected candidate without assuming quote/lot data is present."""
    ticker = analysis.ticker
    price = current_prices.get(ticker)
    valid_price = (
        isinstance(price, (int, float))
        and not isinstance(price, bool)
        and math.isfinite(price)
        and price > 0
    )
    lot_size = lot_sizes.get(ticker)
    valid_lot_size = (
        isinstance(lot_size, int)
        and not isinstance(lot_size, bool)
        and lot_size > 0
    )
    price_label = (
        f"{price:.2f}" if valid_price
        else "unavailable (no verified fresh quote)"
    )
    lot_label = (
        str(lot_size) if valid_lot_size
        else "unavailable (missing/invalid lot size)"
    )
    return (
        f"- {ticker}: price={price_label}, lot={lot_label}, "
        f"score={analysis.score:.4f}"
    )


def _evaluate_decisions(intelligence_results, portfolio):
    """Convert L1-L15 aggregate results into cycle recommendations."""
    return DecisionEngine().evaluate(
        intelligence_results,
        held_tickers=set(portfolio.positions),
    )


def _print_cycle_result(
    portfolio,
    result,
    sell_trades,
    buy_trades,
    equity,
    stats,
    take_profit_percent,
    intelligence_results=None,
    decisions=None,
    equity_complete: bool = True,
    reserve_added_this_cycle: float = 0.0,
) -> None:
    print("REAL T-INVEST MARKET SCAN + VIRTUAL EXECUTION")
    print("Virtual initial balance:", f"{portfolio.initial_balance:.2f} RUB")
    print("Virtual cash (available for trading):", f"{portfolio.cash:.2f} RUB")
    print("Protected profit reserve (not available for trading):", f"{portfolio.protected_cash:.2f} RUB")
    print("Realized P&L:", f"{portfolio.realized_pnl:.2f} RUB")
    print("Total commissions:", f"{portfolio.commissions:.2f} RUB")
    if equity_complete:
        print("Virtual equity:", f"{equity:.2f} RUB")
        print("Total P&L:", f"{stats.total_pnl:.2f} RUB")
        print("Total return:", f"{stats.total_return_pct:.2f} %")
    else:
        print("Virtual equity: PARTIAL", f"{equity:.2f} RUB (unpriced holdings excluded)")
        print("Total P&L / return: NOT REPORTED because full portfolio valuation is unavailable")

    print("Portfolio statistics:" if equity_complete else
          "Portfolio statistics (trade history only; equity/drawdown metrics are not comparable):")
    print(f"- Total trades: {stats.total_trades}")
    print(f"- BUY trades: {stats.buy_trades}")
    print(f"- SELL trades: {stats.sell_trades}")
    print(f"- Profitable SELL trades: {stats.profitable_trades}")
    print(f"- Losing SELL trades: {stats.losing_trades}")
    print(f"- Win rate: {stats.win_rate_pct:.2f} %")
    print(f"- Best realized trade: {stats.best_realized_trade:.2f} RUB")
    print(f"- Worst realized trade: {stats.worst_realized_trade:.2f} RUB")
    print(f"- Average profitable trade: {stats.average_profitable_trade:.2f} RUB")
    print(f"- Average losing trade: {stats.average_losing_trade:.2f} RUB")
    print(f"- Peak equity: {stats.peak_equity:.2f} RUB")
    print(f"- Max drawdown: {stats.max_drawdown:.2f} RUB")
    print(f"- Max drawdown: {stats.max_drawdown_pct:.2f} %")

    detail_limit = 10
    verbose_logs = os.getenv("RNB_VERBOSE_LOGS", "").strip().lower() in {"1", "true", "yes"}

    print(f"Intelligence L1-L15: {len(intelligence_results or {})} инструментов.")
    if intelligence_results:
        ranked_intelligence = sorted(
            intelligence_results.items(),
            key=lambda item: (-item[1].overall_score, item[0]),
        )
        visible_intelligence = ranked_intelligence if verbose_logs else ranked_intelligence[:detail_limit]
        for ticker, intelligence in visible_intelligence:
            print(
                f"- {ticker}: score={intelligence.overall_score:.4f}, "
                f"confidence={intelligence.overall_confidence:.4f}, "
                f"consistency={intelligence.overall_consistency:.4f}"
            )
        if not verbose_logs and len(ranked_intelligence) > detail_limit:
            print(f"- ... ещё {len(ranked_intelligence) - detail_limit} инструментов скрыто; "
                  "RNB_VERBOSE_LOGS=1 покажет полный список.")
    else:
        print("- нет корректных результатов Intelligence")

    print(f"Рекомендации DecisionEngine: {len(decisions or {})}.")
    if decisions:
        ranked_decisions = sorted(decisions.items())
        visible_decisions = ranked_decisions if verbose_logs else ranked_decisions[:detail_limit]
        for ticker, decision in visible_decisions:
            metrics = ""
            if decision.score is not None:
                metrics = (
                    f" | score={decision.score:.4f}"
                    f" confidence={decision.confidence:.4f}"
                    f" consistency={decision.consistency:.4f}"
                )
            print(f"- {ticker}: {decision.action} — {decision.reason}{metrics}")
        if not verbose_logs and len(ranked_decisions) > detail_limit:
            print(f"- ... ещё {len(ranked_decisions) - detail_limit} рекомендаций скрыто; "
                  "RNB_VERBOSE_LOGS=1 покажет полный список.")
    else:
        print("- рекомендаций нет")

    print("Position decisions (existing execution rules):")
    for ticker, position in portfolio.positions.items():
        analysis = result.analyses.get(ticker)
        price = result.current_prices.get(ticker)
        if analysis is None or price is None:
            action = "HOLD"
            reason = "нет свежего анализа"
        elif price / position.average_price - 1.0 >= take_profit_percent / 100.0:
            action = "SELL"
            reason = f"достигнут Take Profit +{take_profit_percent:g}%"
        elif (
            price / position.average_price - 1.0 - portfolio.commission_rate
            <= -0.05
        ):
            action = "SELL"
            reason = "достигнут лимит убытка -5%"
        elif analysis.momentum <= -0.02 and analysis.trend_strength < 0:
            action = "SELL"
            reason = "моментум и тренд стали отрицательными"
        else:
            action = "HOLD"
            reason = "сигнал продажи отсутствует"
        print(f"- {ticker}: {action} — {reason}")

    print("Open-position health review (all holdings):")
    for ticker in sorted(portfolio.positions):
        analysis = result.analyses.get(ticker)
        health = assess_position_health(
            ticker,
            result.candle_history.get(ticker, ()),
            current_price_available=ticker in result.current_prices,
            momentum=getattr(analysis, "momentum", None),
            trend_strength=getattr(analysis, "trend_strength", None),
        )
        range_text = (
            f"{health.recent_range_pct * 100:.3f}%"
            if health.recent_range_pct is not None
            else "not_enough_sessions"
        )
        print(
            f"- {ticker}: status={health.status} "
            f"candles={health.candles_checked} flat_sessions={health.flat_sessions} "
            f"10_session_range={range_text} "
            f"recommendation={health.recommendation}"
        )

    print()
    print("=" * 72)
    print("OPEN PORTFOLIO VALUATION — MARK-TO-MARKET")
    print("=" * 72)
    performances = portfolio.position_performance(result.current_prices)
    missing_performance = sorted(
        set(portfolio.positions) - {item.ticker for item in performances}
    )
    invested_total = sum(item.invested_value for item in performances)
    market_value_total = sum(item.current_value for item in performances)
    unrealized_pnl_total = sum(item.unrealized_pnl for item in performances)
    estimated_sell_commission_total = sum(
        item.estimated_sell_commission for item in performances
    )
    net_if_sold_total = sum(item.net_if_sold_now for item in performances)
    valued_return_pct = (
        unrealized_pnl_total / invested_total * 100.0 if invested_total else 0.0
    )
    net_return_pct = (
        net_if_sold_total / invested_total * 100.0 if invested_total else 0.0
    )
    valuation_status = "PARTIAL — NOT FULL PORTFOLIO VALUE" if missing_performance else "COMPLETE"
    print(f"VALUATION STATUS: {valuation_status}")
    print(f"Open positions: {len(portfolio.positions)}")
    print(f"Positions with fresh prices: {len(performances)}")
    print(f"Invested value (priced positions): {invested_total:.2f} RUB")
    print(f"Current market value (priced positions): {market_value_total:.2f} RUB")
    print(f"Unrealized P&L before estimated exit costs: {unrealized_pnl_total:+.2f} RUB ({valued_return_pct:+.2f}%)")
    print(f"Estimated sell commission: {estimated_sell_commission_total:.2f} RUB")
    print(f"Estimated net P&L if priced positions sold now: {net_if_sold_total:+.2f} RUB ({net_return_pct:+.2f}%)")
    if missing_performance:
        print(
            "WARNING: Full open-portfolio valuation is unavailable. No prices were "
            "invented for these positions: " + ", ".join(missing_performance)
        )
        print("Totals above cover priced positions only and MUST NOT be read as full-portfolio totals.")
    print("-" * 72)
    if performances:
        for performance in performances:
            print(f"- {performance.ticker}")
            print(f"  Quantity: {performance.quantity}")
            print(f"  Average price: {performance.average_price:.2f} RUB")
            print(f"  Market price: {performance.market_price:.2f} RUB")
            print(f"  Invested: {performance.invested_value:.2f} RUB")
            print(f"  Current value: {performance.current_value:.2f} RUB")
            print(f"  Unrealized P&L: {performance.unrealized_pnl:.2f} RUB")
            print(f"  Return: {performance.unrealized_return_pct:.2f} %")
            print(
                "  Estimated sell commission: "
                f"{performance.estimated_sell_commission:.2f} RUB"
            )
            print(
                "  Net if sold now: "
                f"{performance.net_if_sold_now:.2f} RUB "
                f"({performance.net_return_pct_if_sold_now:.2f} %)"
            )
    else:
        print("- none")

    print("Selected 3:")
    for analysis in result.selected_3:
        print(
            _format_selected_analysis_line(
                analysis, result.current_prices, result.lot_sizes
            )
        )

    print("Virtual SELL trades this cycle:")
    for trade in sell_trades:
        print(
            f"- SELL {trade.ticker}: quantity={trade.quantity}, "
            f"price={trade.price:.2f}, commission={trade.commission:.2f}, "
            f"entry_price={trade.entry_price if trade.entry_price is not None else 'unknown'}, "
            f"reason={trade.reason}, P&L={trade.realized_pnl:.2f}"
        )

    print("Virtual BUY trades this cycle:")
    for trade in buy_trades:
        print(
            f"- BUY {trade.ticker}: quantity={trade.quantity}, "
            f"price={trade.price:.2f}, commission={trade.commission:.2f}, "
            f"reason={trade.reason}"
        )

    _print_readable_cycle_summary(
        portfolio=portfolio,
        result=result,
        sell_trades=sell_trades,
        buy_trades=buy_trades,
        equity=equity,
        equity_complete=equity_complete,
        intelligence_results=intelligence_results,
        decisions=decisions,
        reserve_added_this_cycle=reserve_added_this_cycle,
    )


def _print_readable_cycle_summary(
    *,
    portfolio,
    result,
    sell_trades,
    buy_trades,
    equity: float,
    equity_complete: bool,
    intelligence_results=None,
    decisions=None,
    reserve_added_this_cycle: float = 0.0,
    scope_label: str = "Цикл",
) -> None:
    """Print a readable portfolio valuation with explicit completeness and cash reconciliation."""
    trades = [*sell_trades, *buy_trades]
    current_prices = getattr(result, "current_prices", {}) or {}
    positions = getattr(portfolio, "positions", {}) or {}
    missing_quotes = sorted(
        ticker for ticker in positions
        if not _is_valid_report_price(current_prices.get(ticker))
    )
    performances = []
    unpriced_cost_basis = 0.0
    total_cost_basis = 0.0
    commission_rate = float(getattr(portfolio, "commission_rate", 0.0) or 0.0)

    for ticker, position in sorted(positions.items()):
        quantity = getattr(position, "quantity", None)
        average_price = getattr(position, "average_price", None)
        valid_position = (
            isinstance(quantity, (int, float)) and not isinstance(quantity, bool)
            and quantity > 0
            and isinstance(average_price, (int, float)) and not isinstance(average_price, bool)
            and average_price > 0
        )
        if not valid_position:
            continue
        invested = float(quantity) * float(average_price)
        total_cost_basis += invested
        if ticker in missing_quotes:
            unpriced_cost_basis += invested
            continue
        price = float(current_prices[ticker])
        market_value = float(quantity) * price
        gross_unrealized = market_value - invested
        estimated_buy_commission = invested * commission_rate
        estimated_exit_commission = market_value * commission_rate
        net_if_sold = gross_unrealized - estimated_buy_commission - estimated_exit_commission
        performances.append({
            "ticker": ticker, "quantity": quantity,
            "average_price": float(average_price), "market_price": price,
            "invested": invested, "market_value": market_value,
            "unrealized": gross_unrealized,
            "exit_commission": estimated_exit_commission,
            "net_if_sold": net_if_sold,
        })

    known_market_value = sum(item["market_value"] for item in performances)
    known_invested_value = sum(item["invested"] for item in performances)
    known_unrealized = sum(item["unrealized"] for item in performances)
    estimated_exit_commissions = sum(item["exit_commission"] for item in performances)
    known_net_if_sold = sum(item["net_if_sold"] for item in performances)
    cash = float(getattr(portfolio, "cash", 0.0) or 0.0)
    reserve = float(getattr(portfolio, "protected_cash", 0.0) or 0.0)
    initial_balance = getattr(portfolio, "initial_balance", None)
    realized_pnl = float(getattr(portfolio, "realized_pnl", 0.0) or 0.0)
    commissions = float(getattr(portfolio, "commissions", 0.0) or 0.0)
    priced_position_count = len(performances)
    missing_position_count = len(missing_quotes)
    known_assets_total = cash + reserve + known_market_value

    print()
    print("=" * 20 + " RNB — СОСТОЯНИЕ ПОРТФЕЛЯ " + "=" * 20)
    print("Режим: виртуальная торговля; реальные биржевые заявки отключены.")
    print(f"{scope_label}: {'совершены сделки' if trades else 'сделок не было'}; покупок={len(buy_trades)}, продаж={len(sell_trades)}.")
    if initial_balance is not None:
        print(f"1. Стартовый капитал: {float(initial_balance):.2f} RUB.")
    print()
    print("2. ДЕНЬГИ")
    print(f"   Свободные деньги для торговли: {cash:.2f} RUB.")
    print(f"   Защищённый резерв прибыли на данный момент: {reserve:.2f} RUB (недоступен для покупок).")
    print(f"   Отложено в резерв за этот цикл: {max(0.0, reserve_added_this_cycle):.2f} RUB.")
    print(f"   Свободные деньги + защищённый резерв: {cash + reserve:.2f} RUB.")
    print()
    print("3. ОТКРЫТЫЕ ПОЗИЦИИ")
    print(f"   Всего позиций: {len(positions)}; с подтверждённой свежей ценой: {priced_position_count}; без цены: {missing_position_count}.")
    print(f"   Себестоимость всех позиций по цене покупки: {total_cost_basis:.2f} RUB.")
    print(f"   Текущая стоимость оценённых позиций: {known_market_value:.2f} RUB.")
    print(f"   Себестоимость оценённых позиций: {known_invested_value:.2f} RUB.")
    print(f"   Нереализованный P/L оценённых позиций (до комиссии будущей продажи): {known_unrealized:+.2f} RUB.")
    print(f"   Оценочная комиссия продажи оценённых позиций: {estimated_exit_commissions:.2f} RUB.")
    print(f"   Результат оценённых позиций при продаже сейчас, с комиссиями покупки и продажи: {known_net_if_sold:+.2f} RUB.")
    if missing_quotes:
        print("   НЕТ СВЕЖЕЙ ЦЕНЫ: " + ", ".join(missing_quotes) + ".")
        print(f"   Их себестоимость по цене покупки: {unpriced_cost_basis:.2f} RUB; это НЕ текущая рыночная стоимость.")
    else:
        print("   Свежие подтверждённые котировки получены по всем открытым позициям.")
    print()
    print("4. ГДЕ НАХОДЯТСЯ ДЕНЬГИ СЕЙЧАС")
    print(f"   Деньги + резерв + рыночная стоимость оценённых позиций: {known_assets_total:.2f} RUB.")
    if missing_quotes:
        print("   Это только частичный итог: стоимость позиций без свежих котировок не включена.")
        print("   Поэтому разницу со стартовым капиталом нельзя считать убытком; полная оценка пока невозможна.")
    else:
        print(f"   Полная стоимость портфеля (деньги + резерв + все позиции): {equity:.2f} RUB.")
    print()
    print("5. ФИНАНСОВЫЙ РЕЗУЛЬТАТ")
    cycle_realized_pnl = sum(float(getattr(trade, "realized_pnl", 0.0) or 0.0) for trade in sell_trades)
    cycle_positive_profit = sum(max(float(getattr(trade, "realized_pnl", 0.0) or 0.0), 0.0) for trade in sell_trades)
    print(f"   Заработано за этот цикл на закрытых сделках (после комиссий): {cycle_realized_pnl:+.2f} RUB.")
    print(f"   Положительная прибыль закрытых сделок до распределения: {cycle_positive_profit:.2f} RUB.")
    print(f"   Всего реализованная прибыль/убыток за всё время: {realized_pnl:+.2f} RUB (комиссии повторно не вычитаются).")
    print(f"   Все комиссии в истории операций: {commissions:.2f} RUB.")
    if equity_complete:
        if initial_balance is not None and float(initial_balance) > 0:
            total_pnl = float(equity) - float(initial_balance)
            total_return = total_pnl / float(initial_balance) * 100.0
            print(f"   ОБЩИЙ результат против старта: {total_pnl:+.2f} RUB ({total_return:+.2f}%).")
        else:
            print("   Общий P/L против старта не рассчитан: стартовый капитал недоступен.")
        print("   Полнота оценки: ПОЛНАЯ.")
    else:
        print("   ОБЩИЙ P/L и доходность против старта: НЕ РАССЧИТЫВАЮТСЯ — оценка портфеля неполная.")
        print("   Полнота оценки: НЕПОЛНАЯ; не подменять отсутствующие котировки ценой покупки.")
    print()
    print("6. ПОЗИЦИИ ПО ОТДЕЛЬНОСТИ (RUB)")
    if not positions:
        print("   Открытых позиций нет.")
    else:
        for ticker, position in sorted(positions.items()):
            quantity = getattr(position, "quantity", None)
            average_price = getattr(position, "average_price", None)
            if ticker in missing_quotes:
                details = []
                if quantity is not None:
                    details.append(f"количество={quantity}")
                if isinstance(average_price, (int, float)) and not isinstance(average_price, bool):
                    details.append(f"цена покупки={float(average_price):.2f}")
                print(f"   {ticker}: {'; '.join(details) or 'данные позиции неполные'}; текущая цена, стоимость и P/L неизвестны.")
                continue
            item = next((entry for entry in performances if entry["ticker"] == ticker), None)
            if item is None:
                print(f"   {ticker}: свежая цена есть, но количество или цена покупки недоступны.")
                continue
            print(
                f"   {ticker}: кол-во={item['quantity']}; покупка={item['average_price']:.2f}; "
                f"цена сейчас={item['market_price']:.2f}; стоимость={item['market_value']:.2f}; "
                f"нереализованный P/L={item['unrealized']:+.2f}; P/L при продаже сейчас={item['net_if_sold']:+.2f}."
            )
    print()
    print("7. РАБОТА АНАЛИЗА")
    print(f"   Результаты L1–L15: {len(intelligence_results or {})} инструментов.")
    print(f"   Решения DecisionEngine: {len(decisions or {})} рекомендаций.")
    print("   История портфеля и операций сохраняется в SQLite.")
    print("   L11: сбор результатов виден в журнале; фактическое обновление параметров модели этим отчётом не подтверждается.")
    print("=" * 78)



def _is_valid_report_price(price) -> bool:
    """Return whether a quote is a finite positive numeric value."""
    import math
    return isinstance(price, (int, float)) and not isinstance(price, bool) and math.isfinite(price) and price > 0


if __name__ == "__main__":
    main()
