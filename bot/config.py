import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    invest_token: str
    initial_virtual_balance: float = 10_000.0
    commission_rate: float = 0.0005

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("INVEST_TOKEN", "").strip()
        if not token:
            raise ValueError("INVEST_TOKEN is not configured")

        balance = float(os.getenv("VIRTUAL_INITIAL_BALANCE", "10000"))
        commission = float(os.getenv("VIRTUAL_COMMISSION_RATE", "0.0005"))

        if balance <= 0:
            raise ValueError("VIRTUAL_INITIAL_BALANCE must be positive")
        if commission < 0:
            raise ValueError("VIRTUAL_COMMISSION_RATE must not be negative")

        return cls(
            invest_token=token,
            initial_virtual_balance=balance,
            commission_rate=commission,
        )
