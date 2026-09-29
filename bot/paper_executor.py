from __future__ import annotations

from datetime import datetime, timezone

from bot.live_runner import LiveScanResult
from bot.position_sizer import PositionSizer
from bot.virtual_portfolio import VirtualPortfolio


class PaperExecutor:
    """Execute selected real-market prices against the virtual portfolio only."""

    def execute(self, portfolio: VirtualPortfolio, scan: LiveScanResult) -> list:
        if not scan.selected_3:
            return []

        plans = PositionSizer(
            commission_rate=portfolio.commission_rate,
        ).plan(
            cash=portfolio.cash,
            analyses=scan.selected_3,
            prices=scan.current_prices,
            lot_sizes=scan.lot_sizes,
        )

        trades = []
        for plan in plans:
            trades.append(
                portfolio.buy(
                    ticker=plan.ticker,
                    quantity=plan.quantity,
                    price=plan.price,
                    timestamp=datetime.now(timezone.utc),
                )
            )

        return trades
