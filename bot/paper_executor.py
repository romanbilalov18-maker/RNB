from __future__ import annotations

from datetime import datetime, timezone

from bot.live_runner import LiveScanResult
from bot.virtual_portfolio import VirtualPortfolio


class PaperExecutor:
    """Execute selected real-market prices against the virtual portfolio only."""

    def execute(self, portfolio: VirtualPortfolio, scan: LiveScanResult) -> list:
        if not scan.selected_3:
            return []

        budget_per_position = portfolio.cash / len(scan.selected_3)
        trades = []

        for analysis in scan.selected_3:
            ticker = analysis.ticker
            price = scan.current_prices[ticker]
            lot = scan.lot_sizes[ticker]

            unit_cost = price * lot
            commission_multiplier = 1.0 + portfolio.commission_rate
            quantity = int(
                budget_per_position
                / (unit_cost * commission_multiplier)
            ) * lot

            if quantity <= 0:
                continue

            trade = portfolio.buy(
                ticker=ticker,
                quantity=quantity,
                price=price,
                timestamp=datetime.now(timezone.utc),
            )
            trades.append(trade)

        return trades
