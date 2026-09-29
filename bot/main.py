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
        result = LiveMarketRunner(client).run()
        trades = PaperExecutor().execute(portfolio, result)

    store.save(portfolio)

    market_prices = dict(result.current_prices)
    for ticker in portfolio.positions:
        if ticker not in market_prices:
            market_prices[ticker] = _get_position_price(
                result,
                ticker,
            )

    equity = portfolio.equity(market_prices)

    print("REAL T-INVEST MARKET SCAN + VIRTUAL EXECUTION")
    print("Virtual initial balance:", f"{portfolio.initial_balance:.2f} RUB")
    print("Virtual cash:", f"{portfolio.cash:.2f} RUB")
    print("Realized P&L:", f"{portfolio.realized_pnl:.2f} RUB")
    print("Total commissions:", f"{portfolio.commissions:.2f} RUB")
    print("Virtual equity:", f"{equity:.2f} RUB")
    print("Open positions:")

    if portfolio.positions:
        for ticker, position in portfolio.positions.items():
            print(
                f"- {ticker}: quantity={position.quantity}, "
                f"average_price={position.average_price:.2f}, "
                f"market_price={market_prices.get(ticker, 0):.2f}"
            )
    else:
        print("- none")

    print("Selected 3:")
    for analysis in result.selected_3:
        ticker = analysis.ticker
        print(
            f"- {ticker}: price={result.current_prices[ticker]:.2f}, "
            f"lot={result.lot_sizes[ticker]}, "
            f"score={analysis.score:.4f}"
        )

    print("Virtual trades this cycle:")
    for trade in trades:
        print(
            f"- {trade.side} {trade.ticker}: "
            f"quantity={trade.quantity}, price={trade.price:.2f}, "
            f"commission={trade.commission:.2f}"
        )


def _get_position_price(result, ticker: str) -> float:
    if ticker in result.current_prices:
        return result.current_prices[ticker]
    raise ValueError(
        f"Current market price for held position {ticker} was not returned"
    )


if __name__ == "__main__":
    main()
