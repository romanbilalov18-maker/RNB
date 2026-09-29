from __future__ import annotations

from bot.config import Config
from bot.live_runner import LiveMarketRunner
from bot.paper_executor import PaperExecutor
from bot.virtual_portfolio import VirtualPortfolio
from t_tech.invest import Client


def main() -> None:
    config = Config.from_env()
    portfolio = VirtualPortfolio(
        initial_balance=config.initial_virtual_balance,
        commission_rate=config.commission_rate,
    )

    with Client(config.invest_token) as client:
        result = LiveMarketRunner(client).run()
        trades = PaperExecutor().execute(portfolio, result)

    print("REAL T-INVEST MARKET SCAN + VIRTUAL EXECUTION")
    print("Virtual balance:", f"{config.initial_virtual_balance:.2f} RUB")
    print("Selected 3:")
    for analysis in result.selected_3:
        ticker = analysis.ticker
        print(
            f"- {ticker}: price={result.current_prices[ticker]:.2f}, "
            f"lot={result.lot_sizes[ticker]}, "
            f"score={analysis.score:.4f}"
        )

    print("Virtual BUY trades:")
    for trade in trades:
        print(
            f"- {trade.ticker}: quantity={trade.quantity}, "
            f"price={trade.price:.2f}, commission={trade.commission:.2f}"
        )

    print("Virtual cash remaining:", f"{portfolio.cash:.2f} RUB")
    print("Virtual equity:", f"{portfolio.equity(result.current_prices):.2f} RUB")


if __name__ == "__main__":
    main()
