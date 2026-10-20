from __future__ import annotations

from datetime import datetime, timezone

from bot.live_runner import LiveScanResult
from bot.position_manager import PositionManager
from bot.position_sizer import PositionSizer
from bot.virtual_portfolio import VirtualPortfolio


class PaperExecutor:
    """Execute virtual sells first, then size new virtual buys."""

    @staticmethod
    def _has_valid_market_sizing_data(scan: LiveScanResult, ticker: str) -> bool:
        price = scan.current_prices.get(ticker)
        lot_size = scan.lot_sizes.get(ticker)
        return (
            isinstance(price, (int, float))
            and not isinstance(price, bool)
            and 0 < price < float("inf")
            and isinstance(lot_size, int)
            and not isinstance(lot_size, bool)
            and lot_size > 0
        )

    def __init__(self, max_position_weight: float = 0.35, take_profit: float = 0.0015):
        self.position_manager = PositionManager(take_profit=take_profit)
        self.max_position_weight = max_position_weight

    def execute(
        self,
        portfolio: VirtualPortfolio,
        scan: LiveScanResult,
        eligible_buy_tickers: set[str] | None = None,
        eligible_buy_reasons: dict[str, str] | None = None,
    ) -> tuple[list, list]:
        active_tickers = getattr(scan, "active_trading_tickers", None)
        active_analyses = {
            ticker: analysis
            for ticker, analysis in scan.analyses.items()
            if active_tickers is None or ticker in active_tickers
        }
        if active_tickers is not None and not active_tickers:
            print(
                "EXECUTION DIAGNOSTIC: no entries/exits considered; "
                "no instrument passed strict active-session + fresh-quote checks."
            )
            return [], []

        decisions = self.position_manager.evaluate(
            portfolio,
            active_analyses,
            scan.current_prices,
        )
        sell_trades = self.position_manager.execute_sales(
            portfolio,
            decisions,
            scan.current_prices,
        )
        recently_sold = {trade.ticker for trade in sell_trades}
        sell_decision_tickers = {
            decision.ticker
            for decision in decisions
            if decision.action == "SELL"
        }

        existing_values = {
            ticker: position.quantity * scan.current_prices[ticker]
            for ticker, position in portfolio.positions.items()
            if ticker in scan.current_prices
        }
        # Missing quotes for unrelated holdings must not abort execution for
        # eligible instruments. The partial valuation excludes unpriced positions,
        # making position-weight limits conservative rather than inventing prices.
        partial_equity = getattr(portfolio, "equity_with_available_prices", None)
        if callable(partial_equity):
            total_equity, unpriced_positions = partial_equity(scan.current_prices)
        else:
            # Preserve compatibility with lightweight portfolio doubles used by
            # integrations/tests; production VirtualPortfolio implements the
            # quote-aware valuation API above.
            total_equity = portfolio.equity(scan.current_prices)
            unpriced_positions = ()
        if unpriced_positions:
            print(
                "EXECUTION DIAGNOSTIC: portfolio valuation incomplete; "
                f"unpriced_positions={','.join(unpriced_positions)}; "
                "new orders still require fresh prices for their own tickers."
            )
        # After selling, immediately reuse the freed cash. The primary
        # strategy remains TOP-3, but if a TOP-3 candidate is unavailable,
        # walk through the full ranked candidate list from this scan.
        blocked_reentries = self._blocked_reentries(
            portfolio,
            scan.analyses,
        )
        eligible_analyses = []
        rejection_counts = {}
        for analysis in scan.buy_candidates:
            ticker = analysis.ticker
            reasons = []
            if eligible_buy_tickers is not None and ticker not in eligible_buy_tickers:
                reasons.append("DecisionEngine did not authorize BUY")
            if ticker in recently_sold:
                reasons.append("sold this cycle")
            if ticker in sell_decision_tickers:
                reasons.append("PositionManager marked ticker SELL")
            if ticker in blocked_reentries:
                reasons.append("re-entry blocked until weak signal recovers")
            if not self._has_valid_market_sizing_data(scan, ticker):
                if ticker not in scan.current_prices:
                    reasons.append("no verified fresh quote")
                if ticker not in scan.lot_sizes:
                    reasons.append("missing/invalid T-Invest lot size")
                price = scan.current_prices.get(ticker)
                if price is not None and not (
                    isinstance(price, (int, float))
                    and not isinstance(price, bool)
                    and 0 < price < float("inf")
                ):
                    reasons.append("invalid price")
            if active_tickers is not None and ticker not in active_tickers:
                reasons.append("instrument not confirmed active with fresh quote")
            if reasons:
                for reason in reasons:
                    rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                print(f"BUY CANDIDATE REJECTED: {ticker}: {'; '.join(reasons)}")
                continue
            eligible_analyses.append(analysis)

        print(
            f"EXECUTION DIAGNOSTIC: buy_signals={len(eligible_buy_tickers) if eligible_buy_tickers is not None else 'UNFILTERED'} "
            f"ranked_candidates={len(scan.buy_candidates)} "
            f"eligible_for_sizing={len(eligible_analyses)} "
            f"cash={portfolio.cash:.2f} RUB "
            f"active_fresh_tickers={len(active_tickers) if active_tickers is not None else 'UNVERIFIED'}"
        )
        if rejection_counts:
            print(f"EXECUTION REJECTION COUNTS: {rejection_counts}")

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

        if eligible_analyses and not plans:
            min_lot_costs = []
            for analysis in eligible_analyses:
                price = scan.current_prices[analysis.ticker]
                lot_size = scan.lot_sizes[analysis.ticker]
                min_lot_costs.append(
                    (price * lot_size * (1.0 + portfolio.commission_rate), analysis.ticker, lot_size)
                )
            if min_lot_costs:
                minimum_cost, minimum_ticker, minimum_lot = min(min_lot_costs)
                if minimum_cost > portfolio.cash:
                    print(
                        f"POSITION SIZER REJECTED ALL: cash={portfolio.cash:.2f} RUB; "
                        f"cheapest eligible lot={minimum_ticker} x {minimum_lot} "
                        f"costs {minimum_cost:.2f} RUB including commission."
                    )
                else:
                    print(
                        "POSITION SIZER REJECTED ALL: sufficient cash for at least one lot, "
                        "but no allocation satisfied cash/position-weight constraints."
                    )
        elif plans:
            print(
                f"POSITION SIZER PLANS: {len(plans)}; "
                + ", ".join(
                    f"{plan.ticker} qty={plan.quantity} cost={plan.total_cost:.2f} RUB"
                    for plan in plans
                )
            )

        buy_trades = []
        for plan in plans:
            if (
                plan.ticker in portfolio.positions
                or plan.ticker in recently_sold
                or plan.ticker in sell_decision_tickers
            ):
                continue
            buy_trades.append(
                portfolio.buy(
                    ticker=plan.ticker,
                    quantity=plan.quantity,
                    price=plan.price,
                    timestamp=datetime.now(timezone.utc),
                    reason=(eligible_buy_reasons or {}).get(
                        plan.ticker, "BUY accepted by PositionSizer"
                    ),
                )
            )

        return sell_trades, buy_trades

    @staticmethod
    def _blocked_reentries(
        portfolio: VirtualPortfolio,
        analyses: dict,
    ) -> set[str]:
        """Block re-entry after a SELL while the ticker remains weak.

        The block is derived from the persistent trade history, so it survives
        between cycles and process restarts without adding another database field.
        Once the signal recovers, the ticker becomes eligible again.
        """
        last_trade_by_ticker = {}
        for trade in portfolio.trades:
            last_trade_by_ticker[trade.ticker] = trade

        blocked = set()
        for ticker, trade in last_trade_by_ticker.items():
            if trade.side != "SELL":
                continue

            analysis = analyses.get(ticker)
            if analysis is None:
                blocked.add(ticker)
                continue

            if analysis.momentum <= -0.02 and analysis.trend_strength < 0:
                blocked.add(ticker)

        return blocked
