from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Config:
    execution_mode: str = "paper"
    initial_balance: float = 10_000.0
    max_position_percent: float = 10.0
    commission_rate: float = 0.0005
    position_min_signal_strength: float = 0.10
    ticker: str = "BBG004730N88"
    invest_token: str | None = None
    sandbox_account_id: str | None = None
    model_path: str | None = None
    outcome_model_path: str | None = None
    trading_timezone: str = "Europe/Moscow"
    trading_windows: str = "09:50-11:00=0.20,11:00-19:00=0.20,19:00-23:50=0.20"
    performance_journal_path: str = "data/performance_journal.sqlite3"
    paper_portfolio_path: str = "data/paper_portfolio.sqlite3"
    paper_slippage_rate: float = 0.001
    paper_min_net_profit_percent: float = 0.2
    paper_risk_per_trade_percent: float = 1.0
    paper_stop_loss_percent: float = 2.0
    paper_max_quote_age_seconds: float = 120.0
    market_scan_enabled: bool = True
    market_scan_refresh_seconds: float = 300.0
    market_scan_history_days: int = 1
    market_scan_max_candidates: int = 10
    market_scan_max_universe_instruments: int = 50
    risk_min_confidence: float = 0.20

    def __post_init__(self) -> None:
        if self.execution_mode not in {"paper", "sandbox", "live"}:
            raise ValueError("EXECUTION_MODE must be paper, sandbox or live")
        if self.initial_balance <= 0:
            raise ValueError("INITIAL_BALANCE must be positive")
        if self.commission_rate < 0 or self.paper_slippage_rate < 0:
            raise ValueError("commission and slippage rates must be non-negative")
        if not 0 < self.max_position_percent <= 100:
            raise ValueError("MAX_POSITION_PERCENT must be in (0, 100]")
        if not 0 < self.paper_risk_per_trade_percent <= 100:
            raise ValueError("PAPER_RISK_PER_TRADE_PERCENT must be in (0, 100]")
        if not 0 < self.paper_stop_loss_percent < 100:
            raise ValueError("PAPER_STOP_LOSS_PERCENT must be in (0, 100)")
        if self.paper_min_net_profit_percent < 0:
            raise ValueError("PAPER_MIN_NET_PROFIT_PERCENT must be non-negative")
        if self.paper_max_quote_age_seconds <= 0:
            raise ValueError("PAPER_MAX_QUOTE_AGE_SECONDS must be positive")

    @classmethod
    def from_env(cls) -> "Config":
        mode = os.getenv("EXECUTION_MODE", "paper").strip().lower()
        return cls(
            execution_mode=mode,
            initial_balance=float(os.getenv("INITIAL_BALANCE", "10000")),
            max_position_percent=float(os.getenv("MAX_POSITION_PERCENT", "10")),
            commission_rate=float(os.getenv("COMMISSION_RATE", "0.0005")),
            position_min_signal_strength=float(os.getenv("POSITION_MIN_SIGNAL_STRENGTH", "0.20")),
            ticker=os.getenv("TICKER", "BBG004730N88").strip(),
            invest_token=os.getenv("INVEST_TOKEN") or os.getenv("TINKOFF_TOKEN"),
            sandbox_account_id=os.getenv("SANDBOX_ACCOUNT_ID"),
            model_path=os.getenv("MODEL_PATH"),
            outcome_model_path=os.getenv("OUTCOME_MODEL_PATH"),
            trading_timezone=os.getenv("TRADING_TIMEZONE", "Europe/Moscow").strip(),
            trading_windows=os.getenv("TRADING_WINDOWS", "09:50-11:00=0.20,11:00-19:00=0.20,19:00-23:50=0.20").strip(),
            performance_journal_path=os.getenv("PERFORMANCE_JOURNAL_PATH", "data/performance_journal.sqlite3").strip(),
            paper_portfolio_path=os.getenv("PAPER_PORTFOLIO_PATH", "data/paper_portfolio.sqlite3").strip(),
            paper_slippage_rate=float(os.getenv("PAPER_SLIPPAGE_RATE", "0.001")),
            paper_min_net_profit_percent=float(os.getenv("PAPER_MIN_NET_PROFIT_PERCENT", "0.2")),
            paper_risk_per_trade_percent=float(os.getenv("PAPER_RISK_PER_TRADE_PERCENT", "1.0")),
            paper_stop_loss_percent=float(os.getenv("PAPER_STOP_LOSS_PERCENT", "2.0")),
            paper_max_quote_age_seconds=float(os.getenv("PAPER_MAX_QUOTE_AGE_SECONDS", "120")),
            market_scan_enabled=os.getenv("MARKET_SCAN_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"},
            market_scan_refresh_seconds=float(os.getenv("MARKET_SCAN_REFRESH_SECONDS", "300")),
            market_scan_history_days=int(os.getenv("MARKET_SCAN_HISTORY_DAYS", "1")),
            market_scan_max_candidates=int(os.getenv("MARKET_SCAN_MAX_CANDIDATES", "10")),
            market_scan_max_universe_instruments=int(os.getenv("MARKET_SCAN_MAX_UNIVERSE_INSTRUMENTS", "50")),
            risk_min_confidence=float(os.getenv("RISK_MIN_CONFIDENCE", "0.20")),
        )
