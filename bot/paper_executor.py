from __future__ import annotations

from datetime import datetime, timezone

from bot.live_runner import LiveScanResult
from bot.position_manager import PositionManager
from bot.position_sizer import PositionSizer
from bot.virtual_portfolio import VirtualPortfolio


class PaperExecutor:
    """Execute virtual sells first, then size new virtual buys."""

    def __init__(self):
        self.position_manager = PositionManager()

    def execute(
        self,
        portfolio: VirtualPortfolio,
        scan: LiveScanResult,
    ) -> tuple[list, list]:
        decisions = self.position_manager.evaluate(
            portfolio,
            scan.analyses,
            scan.current_prices,
        )
        sell_trades = self.position_manager.execute_sales(
            portfolio,
            decisions,
            scan.current_prices,
        )

        plans = PositionSizer(
            commission_rate=portfolio.commission_rate,
        ).plan(
            cash=portfolio.cash,
            analyses=scan.selected_3,
            prices=scan.current_prices,
            lot_sizes=scan.lot_sizes,
        )

        buy_trades = []
        held_tickers = set(portfolio.positions)
        for plan in plans:
            if plan.ticker in held_tickers:
                continue
            buy_trades.append(
                portfolio.buy(
                    ticker=plan.ticker,
                    quantity=plan.quantity,
                    price=plan.price,
                    timestamp=datetime.now(timezone.utc),
                )
            )

        return sell_trades, buy_trades
