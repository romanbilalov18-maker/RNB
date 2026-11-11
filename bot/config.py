import math
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    invest_token: str
    initial_virtual_balance: float = 10_000.0
    commission_rate: float = 0.0005
    take_profit_percent: float = 0.15
    profit_reserve_rate: float = 0.7
    portfolio_db_path: str = "data/virtual_portfolio.sqlite3"
    risk_budget_percent: float = 1.0
    estimated_slippage_bps: float = 1.0
    fallback_spread_percent: float = 0.02

    @classmethod
    def from_env(cls) -> "Config":
        # Live order execution is deliberately not implemented. Fail closed if an
        # operator attempts to enable it through environment configuration.
        live_trading_enabled = os.getenv("LIVE_TRADING_ENABLED", "false").strip().lower()
        if live_trading_enabled not in {"false", "0", "no", "off", ""}:
            raise ValueError(
                "LIVE_TRADING_ENABLED is unsupported: live order execution is not implemented; "
                "keep virtual trading only"
            )

        token = os.getenv("INVEST_TOKEN", "").strip()
        if not token:
            raise ValueError("INVEST_TOKEN is not configured")

        try:
            balance = float(os.getenv("VIRTUAL_INITIAL_BALANCE", "10000"))
            commission = float(os.getenv("VIRTUAL_COMMISSION_RATE", "0.0005"))
            take_profit = float(os.getenv("TAKE_PROFIT_PERCENT", "0.15"))
            reserve_rate = float(os.getenv("PROFIT_RESERVE_RATE", "0.7"))
            risk_budget_percent = float(os.getenv("VIRTUAL_RISK_BUDGET_PERCENT", "1.0"))
            estimated_slippage_bps = float(os.getenv("VIRTUAL_ESTIMATED_SLIPPAGE_BPS", "1"))
            fallback_spread_percent = float(os.getenv("VIRTUAL_FALLBACK_SPREAD_PERCENT", "0.02"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Virtual portfolio numeric settings must be valid numbers") from exc

        db_path = os.getenv(
            "VIRTUAL_PORTFOLIO_DB",
            "data/virtual_portfolio.sqlite3",
        ).strip()

        for name, value in (
            ("VIRTUAL_INITIAL_BALANCE", balance),
            ("VIRTUAL_COMMISSION_RATE", commission),
            ("TAKE_PROFIT_PERCENT", take_profit),
            ("PROFIT_RESERVE_RATE", reserve_rate),
            ("VIRTUAL_RISK_BUDGET_PERCENT", risk_budget_percent),
            ("VIRTUAL_ESTIMATED_SLIPPAGE_BPS", estimated_slippage_bps),
            ("VIRTUAL_FALLBACK_SPREAD_PERCENT", fallback_spread_percent),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")

        if balance <= 0:
            raise ValueError("VIRTUAL_INITIAL_BALANCE must be positive")
        if commission < 0:
            raise ValueError("VIRTUAL_COMMISSION_RATE must not be negative")
        if take_profit < 0.15:
            raise ValueError("TAKE_PROFIT_PERCENT must be at least 0.15%")
        if not 0.0 <= reserve_rate <= 1.0:
            raise ValueError("PROFIT_RESERVE_RATE must be between 0 and 1")
        if not 0.0 < risk_budget_percent <= 100.0:
            raise ValueError("VIRTUAL_RISK_BUDGET_PERCENT must be in (0, 100]")
        if not 0.0 <= estimated_slippage_bps <= 10000.0:
            raise ValueError("VIRTUAL_ESTIMATED_SLIPPAGE_BPS must be in [0, 10000]")
        if not 0.0 <= fallback_spread_percent <= 100.0:
            raise ValueError("VIRTUAL_FALLBACK_SPREAD_PERCENT must be in [0, 100]")
        if not db_path:
            raise ValueError("VIRTUAL_PORTFOLIO_DB must not be empty")

        return cls(
            invest_token=token,
            initial_virtual_balance=balance,
            commission_rate=commission,
            take_profit_percent=take_profit,
            profit_reserve_rate=reserve_rate,
            risk_budget_percent=risk_budget_percent,
            estimated_slippage_bps=estimated_slippage_bps,
            fallback_spread_percent=fallback_spread_percent,
            portfolio_db_path=db_path,
        )
