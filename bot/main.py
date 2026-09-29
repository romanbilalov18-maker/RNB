from __future__ import annotations

from bot.config import Config
from bot.live_runner import LiveMarketRunner
from bot.paper_executor import PaperExecutor
from bot.portfolio_store import SQLitePortfolioStore
from t_tech.invest import Client


def main() -> None:
    config = Config.from_env()
    store = SQLitePortfolioStore(config.portfolio_db_path)
    portfolio = store.load_or_create(
        initial_balance=config.initial_virtual_balance,
        commission_rate=config.commission_rate,
    )

    with Client(config.invest_token) as client:
        result = LiveMarketRunner(client).run(
            held_tickers=set(portfolio.positions)
        )
        sell_trades, buy_trades = PaperExecutor().execute(portfolio, result)

    store.save(portfolio)

    equity = portfolio.equity(result.current_prices)

    print("REAL T-INVEST MARKET SCAN + VIRTUAL EXECUTION")
    print("Virtual initial balance:", f"{portfolio.initial_balance:.2f} RUB")
    print("Virtual cash:", f"{portfolio.cash:.2f} RUB")
    print("Realized P&L:", f"{portfolio.realized_pnl:.2f} RUB")
    print("Total commissions:", f"{portfolio.commissions:.2f} RUB")
    print("Virtual equity:", f"{equity:.2f} RUB")

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
    if portfolio.positions:
        for ticker, position in portfolio.positions.items():
            print(
                f"- {ticker}: quantity={position.quantity}, "
                f"average_price={position.average_price:.2f}, "
                f"market_price={result.current_prices[ticker]:.2f}"
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
