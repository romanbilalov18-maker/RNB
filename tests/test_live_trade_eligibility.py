import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from bot.live_runner import LiveMarketRunner
from bot.market_context.trading_schedule import ExchangeSession


UTC = timezone.utc


def session(*, verified=True, is_open=True, phase="main"):
    return ExchangeSession(
        exchange="MOEX",
        verified=verified,
        schedule_date="2026-10-19",
        is_trading_day=True,
        session=phase if is_open else "closed",
        phase=phase,
        is_open=is_open,
        next_transition=datetime(2026, 10, 19, 16, tzinfo=UTC),
    )


class LiveTradeEligibilityTests(unittest.TestCase):
    def test_eligible_only_when_all_broker_and_market_gates_pass(self):
        self.assertTrue(
            LiveMarketRunner._instrument_trade_eligible(
                True, "SECURITY_TRADING_STATUS_NORMAL_TRADING",
                session(), True,
            )
        )

    def test_api_trade_unavailable_blocks_trade_even_during_open_session(self):
        self.assertFalse(
            LiveMarketRunner._instrument_trade_eligible(
                False, "SECURITY_TRADING_STATUS_NORMAL_TRADING",
                session(), True,
            )
        )

    def test_stale_quote_blocks_trade_even_during_open_session(self):
        self.assertFalse(
            LiveMarketRunner._instrument_trade_eligible(
                True, "SECURITY_TRADING_STATUS_NORMAL_TRADING",
                session(), False,
            )
        )

    def test_closed_exchange_blocks_trade_even_when_broker_status_says_active(self):
        self.assertFalse(
            LiveMarketRunner._instrument_trade_eligible(
                True, "SECURITY_TRADING_STATUS_NORMAL_TRADING",
                session(is_open=False, phase="calendar_closed"), True,
            )
        )

    def test_unverified_exchange_schedule_blocks_trade(self):
        self.assertFalse(
            LiveMarketRunner._instrument_trade_eligible(
                True, "SECURITY_TRADING_STATUS_NORMAL_TRADING",
                session(verified=False), True,
            )
        )

    def test_inactive_broker_trading_status_blocks_trade(self):
        self.assertFalse(
            LiveMarketRunner._instrument_trade_eligible(
                True, "SECURITY_TRADING_STATUS_NOT_AVAILABLE_FOR_TRADING",
                session(), True,
            )
        )


if __name__ == "__main__":
    unittest.main()
