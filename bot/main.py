from __future__ import annotations

import os
import time

from bot.config import Config
from bot.decision_audit import DecisionAuditStore
from bot.intelligence.decision_engine import DecisionEngine
from bot.intelligence.integration import analyze_scan
from bot.live_runner import LiveMarketRunner
from bot.paper_executor import PaperExecutor
from bot.portfolio_store import SQLitePortfolioStore


def _should_run_another_cycle(remaining_seconds: float, cycle_interval_minutes: float) -> bool:
    """Only start another cycle when more than one full interval remains."""
    return remaining_seconds > cycle_interval_minutes * 60


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

    deadline = time.monotonic() + run_duration_minutes * 60
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
                if active_tickers is not None and not active_tickers:
                    print(
                        "No active T-Invest trading session. Skipping virtual trades, "
                        "portfolio writes and L11 decision-audit observations to avoid "
                        "learning from stale out-of-session quotes."
                    )
                    remaining = deadline - time.monotonic()
                    if not _should_run_another_cycle(remaining, cycle_interval_minutes):
                        print("Runtime limit reached while market session is inactive.")
                        break
                    time.sleep(cycle_interval_minutes * 60)
                    continue
                _validate_held_position_prices(portfolio, result.current_prices)
                learning_observations = audit_store.learning_observations_by_ticker()
                intelligence_results = analyze_scan(
                    result,
                    learning_observations_by_ticker=learning_observations,
                    portfolio=portfolio,
                )
                if active_tickers is not None:
                    intelligence_results = {
                        ticker: intelligence
                        for ticker, intelligence in intelligence_results.items()
                        if ticker in active_tickers
                    }
                decisions = _evaluate_decisions(intelligence_results, portfolio)
                # Only explicit BUY recommendations from a valid L1-L15 result may
                # authorize new virtual entries. Existing PositionManager exits and
                # PositionSizer risk/cash/commission controls remain authoritative.
                eligible_buy_tickers = {
                    ticker for ticker, decision in decisions.items()
                    if decision.action == "BUY"
                }
                eligible_buy_reasons = {
                    ticker: decision.reason
                    for ticker, decision in decisions.items()
                    if decision.action == "BUY"
                }
                sell_trades, buy_trades = PaperExecutor(
                    take_profit=config.take_profit_percent / 100.0
                ).execute(
                    portfolio,
                    result,
                    eligible_buy_tickers=eligible_buy_tickers,
                    eligible_buy_reasons=eligible_buy_reasons,
                )

                equity = portfolio.equity(result.current_prices)
                store.save(portfolio, result.current_prices)
                cycle_id = f"{cycle}:{time.time_ns()}"
                audit_count = _record_cycle_with_retries(
                    audit_store,
                    cycle_id=cycle_id,
                    decisions=decisions,
                    virtual_trades=[*sell_trades, *buy_trades],
                    equity=equity,
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
                )

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



def _validate_held_position_prices(portfolio, market_prices) -> None:
    """Reject stale/missing quote snapshots before mutating the portfolio."""
    missing = sorted(set(portfolio.positions) - set(market_prices))
    if missing:
        raise RuntimeError(
            "Cycle skipped: no verified fresh T-Invest prices for open positions: "
            + ", ".join(missing)
            + ". Portfolio was not changed; inspect T-Invest provenance diagnostics."
        )


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
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


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
) -> None:
    print("REAL T-INVEST MARKET SCAN + VIRTUAL EXECUTION")
    print("Virtual initial balance:", f"{portfolio.initial_balance:.2f} RUB")
    print("Virtual cash:", f"{portfolio.cash:.2f} RUB")
    print("Realized P&L:", f"{portfolio.realized_pnl:.2f} RUB")
    print("Total commissions:", f"{portfolio.commissions:.2f} RUB")
    print("Virtual equity:", f"{equity:.2f} RUB")
    print("Total P&L:", f"{stats.total_pnl:.2f} RUB")
    print("Total return:", f"{stats.total_return_pct:.2f} %")

    print("Portfolio statistics:")
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

    print("Intelligence L1-L15:")
    if intelligence_results:
        for ticker, intelligence in sorted(
            intelligence_results.items(),
            key=lambda item: (-item[1].overall_score, item[0]),
        ):
            print(
                f"- {ticker}: score={intelligence.overall_score:.4f}, "
                f"confidence={intelligence.overall_confidence:.4f}, "
                f"consistency={intelligence.overall_consistency:.4f}"
            )
    else:
        print("- no valid Intelligence results")

    print("Decision Engine recommendations (BUY gates new virtual entries):")
    if decisions:
        for ticker, decision in sorted(decisions.items()):
            metrics = ""
            if decision.score is not None:
                metrics = (
                    f" | score={decision.score:.4f}"
                    f" confidence={decision.confidence:.4f}"
                    f" consistency={decision.consistency:.4f}"
                )
            print(f"- {ticker}: {decision.action} — {decision.reason}{metrics}")
    else:
        print("- no recommendations")

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

    print("Open positions:")
    performances = portfolio.position_performance(result.current_prices)
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
        ticker = analysis.ticker
        print(
            f"- {ticker}: price={result.current_prices[ticker]:.2f}, "
            f"lot={result.lot_sizes[ticker]}, score={analysis.score:.4f}"
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


if __name__ == "__main__":
    main()
