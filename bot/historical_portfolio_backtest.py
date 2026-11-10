"""Run a real-data historical portfolio replay using RNB's paper execution stack.

Input candles must be exported from T-Invest. No synthetic prices or live orders
are used. The current instrument catalog is metadata only and is explicitly
reported as a source of survivorship/point-in-time limitations.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from bot.historical_replay import HistoricalReplay, iter_historical_cycles
from bot.paper_executor import PaperExecutor
from bot.virtual_portfolio import VirtualPortfolio


def load_dataset(
    csv_path: Path,
    *,
    tickers: set[str] | None = None,
) -> tuple[dict[str, list[object]], dict, dict]:
    coverage_path = csv_path.with_suffix(csv_path.suffix + ".coverage.json")
    manifest_path = csv_path.with_suffix(csv_path.suffix + ".manifest.json")
    if not csv_path.is_file() or not coverage_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(
            "Expected T-Invest CSV plus .coverage.json and .manifest.json sidecars"
        )
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if coverage.get("data_source") != "T-Invest API" or manifest.get("data_source") != "T-Invest API":
        raise ValueError("Historical replay accepts only datasets marked as T-Invest API")
    if manifest.get("data_integrity_status") != "unique_symbol_timestamps":
        raise ValueError("Dataset contains duplicate symbol/timestamp rows")

    metadata = {
        str(item.get("ticker") or "").strip().upper(): item
        for item in coverage.get("instrument_records", [])
        if item.get("ticker")
        and item.get("catalog_snapshot_status") == "present_in_current_TInvest_shares_catalog"
    }
    candles: dict[str, list[object]] = {}
    seen = set()
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError("Historical CSV is missing required OHLCV columns")
        for line_number, row in enumerate(reader, start=2):
            ticker = str(row["symbol"] or "").strip().upper()
            if not ticker:
                raise ValueError(f"CSV line {line_number}: empty ticker")
            try:
                stamp = datetime.fromisoformat(str(row["timestamp"]).replace("Z", "+00:00"))
                values = {key: float(row[key]) for key in ("open", "high", "low", "close", "volume")}
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"CSV line {line_number}: invalid timestamp/OHLCV") from exc
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError(f"CSV line {line_number}: timestamp must include timezone")
            if not all(math.isfinite(value) for value in values.values()):
                raise ValueError(f"CSV line {line_number}: non-finite OHLCV")
            if min(values[key] for key in ("open", "high", "low", "close")) <= 0 or values["volume"] < 0:
                raise ValueError(f"CSV line {line_number}: invalid OHLCV bounds")
            if values["high"] < max(values["open"], values["low"], values["close"]):
                raise ValueError(f"CSV line {line_number}: high is inconsistent with OHLC")
            if values["low"] > min(values["open"], values["high"], values["close"]):
                raise ValueError(f"CSV line {line_number}: low is inconsistent with OHLC")
            key = (ticker, stamp)
            if key in seen:
                raise ValueError(f"CSV line {line_number}: duplicate ticker/timestamp")
            seen.add(key)
            candles.setdefault(ticker, []).append(SimpleNamespace(time=stamp, **values))

    if tickers is not None:
        requested = {
            str(ticker).strip().upper()
            for ticker in tickers
            if isinstance(ticker, str) and str(ticker).strip()
        }
        if not requested:
            raise ValueError("ticker filter must contain at least one non-empty symbol")
        missing = sorted(requested - set(candles))
        if missing:
            raise ValueError(
                "requested ticker filter contains symbols absent from T-Invest dataset: "
                + ", ".join(missing)
            )
        candles = {ticker: bars for ticker, bars in candles.items() if ticker in requested}

    for ticker, bars in candles.items():
        bars.sort(key=lambda item: item.time)
        item = metadata.get(ticker)
        if item is None:
            raise ValueError(f"{ticker}: no matching current T-Invest catalog metadata")
        if not item.get("uid") and not item.get("figi"):
            raise ValueError(f"{ticker}: instrument UID/FIGI unavailable")
        lot = item.get("lot")
        # Current catalog metadata is not historical point-in-time lot data.
        if isinstance(lot, bool) or not isinstance(lot, int) or lot <= 0:
            raise ValueError(f"{ticker}: valid current T-Invest lot size unavailable")
    return candles, metadata, manifest



def _build_open_position_report(portfolio, market_prices, equity_curve):
    """Report every remaining holding without inventing marks for missing quotes."""
    performance = {
        item.ticker: item
        for item in portfolio.position_performance(market_prices)
    }
    details = []
    missing_final_quotes = []
    priced_market_value = 0.0
    priced_cost_basis = 0.0

    for ticker, position in sorted(portfolio.positions.items()):
        item = performance.get(ticker)
        cost_basis = position.quantity * position.average_price
        if item is None:
            missing_final_quotes.append(ticker)
            details.append({
                "ticker": ticker,
                "quantity": position.quantity,
                "average_entry_price": position.average_price,
                "cost_basis": cost_basis,
                "market_price": None,
                "market_value": None,
                "unrealized_pnl_before_exit_costs": None,
                "estimated_net_if_sold_now": None,
                "valuation_status": "MISSING_FINAL_QUOTE",
            })
            continue

        priced_market_value += item.current_value
        priced_cost_basis += item.invested_value
        details.append({
            "ticker": ticker,
            "quantity": item.quantity,
            "average_entry_price": item.average_price,
            "cost_basis": item.invested_value,
            "market_price": item.market_price,
            "market_value": item.current_value,
            "unrealized_pnl_before_exit_costs": item.unrealized_pnl,
            "estimated_sell_commission": item.estimated_sell_commission,
            "estimated_net_if_sold_now": item.net_if_sold_now,
            "valuation_status": "PRICED",
        })

    missing_cycles = {}
    incomplete_cycles = 0
    for point in equity_curve:
        if point.unpriced_tickers:
            incomplete_cycles += 1
            for ticker in point.unpriced_tickers:
                missing_cycles[ticker] = missing_cycles.get(ticker, 0) + 1

    summary = {
        "valuation_complete": not missing_final_quotes,
        "priced_positions": len(details) - len(missing_final_quotes),
        "unpriced_positions": len(missing_final_quotes),
        "missing_final_quote_tickers": missing_final_quotes,
        "priced_positions_market_value": priced_market_value,
        "priced_positions_cost_basis": priced_cost_basis,
        "incomplete_mark_to_market_cycles": incomplete_cycles,
        "unpriced_ticker_cycle_counts": dict(sorted(missing_cycles.items())),
    }
    return details, summary

def run_replay(
    csv_path: Path,
    *,
    initial_balance: float = 100_000.0,
    commission_rate: float = 0.0005,
    reserve_rate: float = 0.7,
    risk_budget_percent: float = 1.0,
    take_profit_percent: float = 0.15,
    tickers: set[str] | None = None,
) -> dict:
    candles, metadata, manifest = load_dataset(csv_path, tickers=tickers)
    instrument_ids = {
        ticker: str(item.get("uid") or item.get("figi"))
        for ticker, item in metadata.items() if ticker in candles
    }
    lots = {ticker: int(metadata[ticker]["lot"]) for ticker in candles}
    exchanges = {
        ticker: {"instrument_exchange": str(metadata[ticker].get("exchange") or "").strip()}
        for ticker in candles
    }
    if any(not value["instrument_exchange"] for value in exchanges.values()):
        missing = sorted(ticker for ticker, value in exchanges.items() if not value["instrument_exchange"])
        raise ValueError(f"Missing exchange metadata for: {', '.join(missing)}")

    portfolio = VirtualPortfolio(
        initial_balance=initial_balance,
        commission_rate=commission_rate,
        profit_reserve_rate=reserve_rate,
    )
    executor = PaperExecutor(
        take_profit=take_profit_percent / 100.0,
        risk_budget_pct=risk_budget_percent / 100.0,
    )
    cycles = iter_historical_cycles(
        candles,
        instrument_ids=instrument_ids,
        lot_sizes=lots,
        sessions_by_ticker=exchanges,
        tradable_tickers=set(candles),
        min_history=20,
        momentum_period=10,
        portfolio=portfolio,
        sectors_by_ticker={
            ticker: str(item.get("sector")).strip()
            for ticker, item in metadata.items()
            if isinstance(item.get("sector"), str) and item.get("sector").strip()
        },
    )
    last_scan = None

    def tracked_cycles():
        nonlocal last_scan
        for cycle in cycles:
            last_scan = cycle.scan
            yield cycle

    result = HistoricalReplay(portfolio, executor).run(tracked_cycles())
    final_prices = getattr(last_scan, "current_prices", {}) or {}
    open_position_details, position_valuation = _build_open_position_report(
        portfolio, final_prices, result.equity_curve
    )
    report = {
        "report_type": "RNB_HISTORICAL_PORTFOLIO_REPLAY",
        "data_source": "T-Invest API",
        "execution_mode": "VIRTUAL_ONLY",
        "live_orders_submitted": False,
        "historical_universe_reconstructed": False,
        "known_bias": "Current scanner universe and current catalog metadata; survivorship/selection bias and historical lot-size changes are not reconstructed.",
        "dataset": {
            "symbols": len(candles),
            "candle_rows": sum(len(items) for items in candles.values()),
            "start": manifest.get("sample_start"),
            "end": manifest.get("sample_end"),
            "selection_method": manifest.get("selection_method"),
            "universe_filter": sorted(candles) if tickers is not None else None,
        },
        "settings": {
            "initial_balance": initial_balance,
            "commission_rate_per_side": commission_rate,
            "profit_reserve_rate": reserve_rate,
            "risk_budget_percent": risk_budget_percent,
            "take_profit_percent": take_profit_percent,
            "execution_price": "next daily open; existing-position Stop Loss/Take Profit may fill at a daily OHLC trigger or gap open",
            "intraday_ohlc_ambiguity": "if stop and target are both touched in one daily candle, stop is assumed first (conservative)",
            "signal_data": "only prior completed daily candles; current-day OHLC is execution-only",
        },
        "portfolio": {
            "final_equity": result.final_equity,
            "total_return_pct": result.total_return_pct,
            "realized_pnl": result.realized_pnl,
            "commissions": result.commissions,
            "protected_cash": result.protected_cash,
            "spendable_cash": float(portfolio.cash),
            "open_positions": len(portfolio.positions),
            "open_position_details": open_position_details,
            "position_valuation": position_valuation,
            "total_trades": result.total_trades,
            "buy_trades": result.buy_trades,
            "sell_trades": result.sell_trades,
            "max_drawdown": result.max_drawdown,
            "max_drawdown_pct": result.max_drawdown_pct,
            "warnings": list(result.warnings),
            "decision_diagnostics": result.decision_diagnostics,
        },
        "trades": [
            {
                "timestamp": trade.timestamp.isoformat() if hasattr(trade.timestamp, "isoformat") else str(trade.timestamp),
                "ticker": trade.ticker,
                "side": trade.side,
                "quantity": trade.quantity,
                "price": trade.price,
                "commission": trade.commission,
                "realized_pnl": trade.realized_pnl,
                "reserve_transfer": trade.reserve_transfer,
                "reason": trade.reason,
            }
            for trade in portfolio.trades
        ],
        "equity_curve": [
            {
                "timestamp": point.timestamp.isoformat(),
                "equity": point.equity,
                "cash": point.cash,
                "protected_cash": point.protected_cash,
                "open_positions": point.open_positions,
                "unpriced_tickers": list(point.unpriced_tickers),
            }
            for point in result.equity_curve
        ],
        "limitations": [
            "The historical universe is not reconstructed point-in-time.",
            "Current lot sizes and exchange metadata are used; historical changes are unavailable in the exported dataset.",
            "Daily bars do not reveal intraday event order; when both stop and target are touched in one candle, the replay conservatively assumes the stop occurred first. Bid/ask spread, queue position, and partial fills are not modeled.",
            "The daily candle's existence is used as evidence of a trading day; this is not a full historical exchange schedule.",
            "Results are research diagnostics, not a profitability guarantee or authorization for real-money trading.",
        ],
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path("data/level_01_history.csv"))
    parser.add_argument("--initial-balance", type=float, default=100_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.0005)
    parser.add_argument("--reserve-rate", type=float, default=0.7)
    parser.add_argument("--risk-budget-percent", type=float, default=1.0)
    parser.add_argument("--take-profit-percent", type=float, default=0.15)
    parser.add_argument(
        "--tickers",
        default="",
        help="Optional comma-separated fixed ticker universe; missing symbols fail closed",
    )
    parser.add_argument("--output", type=Path, default=Path("data/historical_portfolio_report.json"))
    args = parser.parse_args()
    if not math.isfinite(args.initial_balance) or args.initial_balance <= 0:
        raise SystemExit("--initial-balance must be finite and positive")
    if not math.isfinite(args.commission_rate) or not 0 <= args.commission_rate <= 1:
        raise SystemExit("--commission-rate must be between 0 and 1")
    if not math.isfinite(args.reserve_rate) or not 0 <= args.reserve_rate <= 1:
        raise SystemExit("--reserve-rate must be between 0 and 1")
    if not math.isfinite(args.risk_budget_percent) or not 0 < args.risk_budget_percent <= 100:
        raise SystemExit("--risk-budget-percent must be in (0, 100]")
    if not math.isfinite(args.take_profit_percent) or not 0.15 <= args.take_profit_percent <= 100:
        raise SystemExit("--take-profit-percent must be in [0.15, 100]")
    report = run_replay(
        args.csv,
        initial_balance=args.initial_balance,
        commission_rate=args.commission_rate,
        reserve_rate=args.reserve_rate,
        risk_budget_percent=args.risk_budget_percent,
        take_profit_percent=args.take_profit_percent,
        tickers=(
            {item.strip().upper() for item in args.tickers.split(",") if item.strip()}
            if args.tickers.strip() else None
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    p = report["portfolio"]
    print("HISTORICAL_PORTFOLIO_REPLAY=COMPLETED")
    print("EXECUTION_MODE=VIRTUAL_ONLY; LIVE_ORDERS_SUBMITTED=False")
    print(f"DATASET_SYMBOLS={report['dataset']['symbols']} CANDLE_ROWS={report['dataset']['candle_rows']}")
    print(f"INITIAL_BALANCE_RUB={args.initial_balance:.2f}")
    print(f"FINAL_EQUITY_RUB={p['final_equity'] if p['final_equity'] is not None else 'INCOMPLETE'}")
    print(f"TOTAL_RETURN_PCT={p['total_return_pct'] if p['total_return_pct'] is not None else 'INCOMPLETE'}")
    print(f"TRADES={p['total_trades']} BUYS={p['buy_trades']} SELLS={p['sell_trades']}")
    print(f"REALIZED_PNL_RUB={p['realized_pnl']:.2f} COMMISSIONS_RUB={p['commissions']:.2f}")
    print(f"SPENDABLE_CASH_RUB={p['spendable_cash']:.2f} PROTECTED_RESERVE_RUB={p['protected_cash']:.2f}")
    print(f"MAX_DRAWDOWN_RUB={p['max_drawdown'] if p['max_drawdown'] is not None else 'INCOMPLETE'}")

    diagnostics = p["decision_diagnostics"]
    print(f"DECISION_CANDIDATES={diagnostics.get('candidate_decisions', 0)}")
    print(f"DECISION_ACTION_COUNTS={json.dumps(diagnostics.get('action_counts', {}), ensure_ascii=False, sort_keys=True)}")
    print(f"DECISION_REASON_COUNTS={json.dumps(diagnostics.get('reason_counts', {}), ensure_ascii=False, sort_keys=True)}")
    print(f"DECISION_METRIC_SUMMARY={json.dumps(diagnostics.get('metric_summary', {}), ensure_ascii=False, sort_keys=True)}")
    print(f"DECISION_CONFIDENCE_BREAKDOWN={json.dumps(diagnostics.get('confidence_breakdown_summary', {}), ensure_ascii=False, sort_keys=True)}")

    print(f"REPORT={args.output}")


if __name__ == "__main__":
    main()
