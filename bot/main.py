from __future__ import annotations

import os
import time

from bot.config import Config
from bot.live_runner import LiveMarketRunner
from bot.paper_executor import PaperExecutor
from bot.portfolio_store import SQLitePortfolioStore
from t_tech.invest import Client


def main() -> None:
    config = Config.from_env()
    run_duration_minutes = _env_positive_float("RUN_DURATION_MINUTES", 1.0)
    cycle_interval_minutes = _env_positive_float("CYCLE_INTERVAL_MINUTES", 5.0)
    if cycle_interval_minutes > run_duration_minutes:
        raise ValueError("CYCLE_INTERVAL_MINUTES must not exceed RUN_DURATION_MINUTES")

    store = SQLitePortfolioStore(config.portfolio_db_path)
    portfolio = store.load_or_create(
        initial_balance=config.initial_virtual_balance,
        commission_rate=config.commission_rate,
    )

    deadline = time.monotonic() + run_duration_minutes * 60
    cycle = 0

    with Client(config.invest_token) as client:
        while True:
            cycle += 1
            print()
            print(f"=== CYCLE {cycle} ===")
            print(f"Runtime limit: {run_duration_minutes:g} min")
            print(f"Cycle interval: {cycle_interval_minutes:g} min")

            result = LiveMarketRunner(client).run(
                held_tickers=set(portfolio.positions)
            )
            sell_trades, buy_trades = PaperExecutor().execute(portfolio, result)

            equity = portfolio.equity(result.current_prices)
            store.save(portfolio, result.current_prices)
            history = store.equity_history()
            stats = portfolio.statistics(equity, history)

            _print_cycle_result(
                portfolio,
                result,
                sell_trades,
                buy_trades,
                equity,
                stats,
            )

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                print(f"Runtime limit reached after cycle {cycle}.")
                break

            sleep_seconds = min(cycle_interval_minutes * 60, remaining)
            print(f"Next cycle in {sleep_seconds / 60:.2f} min.")
            time.sleep(sleep_seconds)


def _env_positive_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


def _print_cycle_result(
    portfolio,
    result,
    sell_trades,
    buy_trades,
    equity,
    stats,
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
    print(f"- Peak equity: {stats.peak_equity:.2f} RUB")
    print(f"- Max drawdown: {stats.max_drawdown:.2f} RUB")
    print(f"- Max drawdown: {stats.max_drawdown_pct:.2f} %")

    print("Position decisions:")
    for ticker, position in portfolio.positions.items():
        analysis = result.analyses.get(ticker)
        if analysis is None:
            action = "HOLD"
            reason = "нет свежего анализа"
        elif analysis.momentum <= -0.02 and analysis.trend_strength < 0:
            action = "SELL"
            reason = "моментум и тренд стали отрицательными"
        elif (
            result.current_prices[ticker] / position.average_price - 1.0
            - portfolio.commission_rate
            <= -0.05
        ):
            action = "SELL"
            reason = "достигнут лимит убытка"
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
            f"P&L={trade.realized_pnl:.2f}"
        )

    print("Virtual BUY trades this cycle:")
    for trade in buy_trades:
        print(
            f"- BUY {trade.ticker}: quantity={trade.quantity}, "
            f"price={trade.price:.2f}, commission={trade.commission:.2f}"
        )


if __name__ == "__main__":
    main()
