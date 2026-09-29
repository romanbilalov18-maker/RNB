import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    invest_token: str
    initial_virtual_balance: float = 10_000.0
    commission_rate: float = 0.0005
    take_profit_percent: float = 5.0
    portfolio_db_path: str = "data/virtual_portfolio.sqlite3"

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("INVEST_TOKEN", "").strip()
        if not token:
            raise ValueError("INVEST_TOKEN is not configured")

        balance = float(os.getenv("VIRTUAL_INITIAL_BALANCE", "10000"))
        commission = float(os.getenv("VIRTUAL_COMMISSION_RATE", "0.0005"))
        take_profit = float(os.getenv("TAKE_PROFIT_PERCENT", "5"))
        db_path = os.getenv(
            "VIRTUAL_PORTFOLIO_DB",
            "data/virtual_portfolio.sqlite3",
        ).strip()

        if balance <= 0:
            raise ValueError("VIRTUAL_INITIAL_BALANCE must be positive")
        if commission < 0:
            raise ValueError("VIRTUAL_COMMISSION_RATE must not be negative")
        if take_profit <= 0:
            raise ValueError("TAKE_PROFIT_PERCENT must be positive")
        if not db_path:
            raise ValueError("VIRTUAL_PORTFOLIO_DB must not be empty")

        return cls(
            invest_token=token,
            initial_virtual_balance=balance,
            commission_rate=commission,
            take_profit_percent=take_profit,
            portfolio_db_path=db_path,
        )
