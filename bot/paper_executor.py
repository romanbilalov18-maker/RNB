from __future__ import annotations

from datetime import datetime, timezone

from bot.live_runner import LiveScanResult
from bot.position_manager import PositionManager
from bot.position_sizer import PositionSizer
from bot.virtual_portfolio import VirtualPortfolio


class PaperExecutor:
    """Execute virtual sells first, then size new virtual buys."""

    def __init__(self, max_position_weight: float = 0.35, take_profit: float = 0.05):
        self.position_manager = PositionManager(take_profit=take_profit)
        self.max_position_weight = max_position_weight

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
        recently_sold = {trade.ticker for trade in sell_trades}

        existing_values = {
            ticker: position.quantity * scan.current_prices[ticker]
            for ticker, position in portfolio.positions.items()
            if ticker in scan.current_prices
        }
        total_equity = portfolio.equity(scan.current_prices)
        eligible_analyses = [
            analysis
            for analysis in scan.selected_3
            if analysis.ticker not in recently_sold
        ]

        plans = PositionSizer(
            commission_rate=portfolio.commission_rate,
            max_position_weight=self.max_position_weight,
        ).plan(
            cash=portfolio.cash,
            analyses=eligible_analyses,
            prices=scan.current_prices,
            lot_sizes=scan.lot_sizes,
            existing_positions=set(portfolio.positions),
            existing_values=existing_values,
            total_equity=total_equity,
        )

        buy_trades = []
        for plan in plans:
            if plan.ticker in portfolio.positions or plan.ticker in recently_sold:
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
