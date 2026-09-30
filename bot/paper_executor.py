from __future__ import annotations

from datetime import datetime, timezone

from bot.live_runner import LiveScanResult
from bot.position_manager import PositionManager
from bot.position_sizer import PositionSizer
from bot.virtual_portfolio import VirtualPortfolio


class PaperExecutor:
    """Execute virtual sells first, then size new virtual buys."""

    def __init__(self, max_position_weight: float = 0.35, take_profit: float = 0.0015):
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
        # After selling, immediately reuse the freed cash. The primary
        # strategy remains TOP-3, but if a TOP-3 candidate is unavailable,
        # walk through the full ranked candidate list from this scan.
        blocked_reentries = self._blocked_reentries(
            portfolio,
            scan.analyses,
        )
        eligible_analyses = [
            analysis
            for analysis in scan.buy_candidates
            if (
                analysis.ticker not in recently_sold
                and analysis.ticker not in blocked_reentries
            )
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

    @staticmethod
    def _blocked_reentries(
        portfolio: VirtualPortfolio,
        analyses: dict,
    ) -> set[str]:
        """Block re-entry while a previously losing exit still has a negative signal.

        The block is derived from the persistent trade history, so it survives
        between cycles and process restarts without adding another database field.
        Once the signal recovers, the ticker becomes eligible again.
        """
        last_trade_by_ticker = {}
        for trade in portfolio.trades:
            last_trade_by_ticker[trade.ticker] = trade

        blocked = set()
        for ticker, trade in last_trade_by_ticker.items():
            if trade.side != "SELL" or trade.realized_pnl >= 0:
                continue

            analysis = analyses.get(ticker)
            if analysis is None:
                blocked.add(ticker)
                continue

            if analysis.momentum <= -0.02 and analysis.trend_strength < 0:
                blocked.add(ticker)

        return blocked
