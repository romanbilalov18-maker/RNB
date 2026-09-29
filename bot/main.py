from __future__ import annotations

from bot.config import Config
from bot.live_runner import LiveMarketRunner
from t_tech.invest import Client


def main() -> None:
    config = Config.from_env()

    with Client(config.invest_token) as client:
        result = LiveMarketRunner(client).run()

    print("REAL T-INVEST MARKET SCAN")
    print("Top 10:")
    for share in result.selected_10:
        print(f"- {getattr(share, 'ticker', '')}: {getattr(share, 'name', '')}")

    print("Selected 3:")
    for analysis in result.selected_3:
        print(
            f"- {analysis.ticker}: "
            f"score={analysis.score:.4f}, "
            f"momentum={analysis.momentum:.4%}, "
            f"volatility={analysis.volatility:.4%}"
        )


if __name__ == "__main__":
    main()
