import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from bot.live_runner import LiveMarketRunner
from bot.market_context.trading_schedule import ExchangeSession


class LiveRunnerExchangeSessionTests(unittest.TestCase):
    def test_resolves_exchange_sessions_for_every_analyzed_instrument(self):
        now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
        analyzed = [
            SimpleNamespace(ticker="NORMAL", exchange="MOEX"),
            SimpleNamespace(ticker="HELD", exchange="SPB"),
        ]

        def resolve(exchange, schedule, observed_at):
            self.assertEqual(observed_at, now)
            return ExchangeSession(
                exchange=exchange, verified=True, schedule_date="2026-10-31",
                is_trading_day=True, session="closed", phase="outside_window",
                is_open=False,
            )

        with patch("bot.live_runner.resolve_exchange_session", side_effect=resolve) as mocked:
            sessions = LiveMarketRunner._exchange_sessions_for_shares(
                analyzed, {"MOEX": object(), "SPB": object()}, now
            )

        self.assertEqual(set(sessions), {"MOEX", "SPB"})
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(sessions["SPB"].exchange, "SPB")

    def test_deduplicates_instruments_on_the_same_exchange(self):
        now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
        analyzed = [
            SimpleNamespace(ticker="A", exchange="MOEX"),
            SimpleNamespace(ticker="B", exchange="MOEX"),
        ]
        resolved = ExchangeSession(
            exchange="MOEX", verified=True, schedule_date="2026-10-31",
            is_trading_day=True, session="closed", phase="outside_window",
            is_open=False,
        )
        with patch("bot.live_runner.resolve_exchange_session", return_value=resolved) as mocked:
            sessions = LiveMarketRunner._exchange_sessions_for_shares(analyzed, {}, now)
        self.assertEqual(set(sessions), {"MOEX"})
        mocked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
