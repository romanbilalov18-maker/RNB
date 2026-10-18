import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from bot.intelligence.decision_engine import DecisionEngine
from bot.intelligence.integration import build_market_snapshot
from bot.intelligence.pipeline.intelligence_pipeline import IntelligencePipeline
from bot.main import _evaluate_decisions


class MarketContextDecisionFlowTests(unittest.TestCase):
    def test_official_session_context_reaches_snapshot_and_full_decision_flow(self):
        session_context = {
            "observed_at_utc": "2026-10-19T10:00:00+00:00",
            "observed_at_moscow": "2026-10-19T13:00:00+03:00",
            "weekday": "Monday",
            "weekday_number": 0,
            "weekday_candidate": True,
            "calendar_status": "weekday_candidate",
            "session": "scheduled_open",
            "session_phase": "main",
            "schedule_verified": True,
            "exchange_sessions": {
                "MOEX": {
                    "exchange": "MOEX",
                    "verified": True,
                    "is_trading_day": True,
                    "session": "main",
                    "phase": "main",
                    "is_open": True,
                }
            },
        }
        instrument_session = {
            "exchange": "MOEX",
            "instrument_exchange": "MOEX",
            "verified": True,
            "is_trading_day": True,
            "session": "main",
            "phase": "main",
            "is_open": True,
            "trading_status": "NORMAL_TRADING",
            "broker_status_allows_session": True,
            "quote_fresh": True,
            "trade_eligible": True,
        }
        analysis = SimpleNamespace(
            ticker="AAA",
            average_volume=1200.0,
            volume_ratio=1.2,
            volatility=0.02,
            momentum=0.03,
        )
        candle = SimpleNamespace(
            time=datetime(2026, 10, 19, 9, 55, tzinfo=timezone.utc),
            open=99.0,
            high=106.0,
            low=98.0,
            close=105.0,
            volume=1200.0,
        )
        scan = SimpleNamespace(
            analyses={"AAA": analysis},
            buy_candidates=[analysis],
            current_prices={"AAA": 105.0},
            previous_closes={"AAA": 100.0},
            lot_sizes={"AAA": 10},
            latest_candles={"AAA": candle},
            candle_history={"AAA": [candle]},
            market_context=SimpleNamespace(to_dict=lambda: session_context),
            session_by_ticker={"AAA": instrument_session},
            market_return=0.01,
            market_breadth=0.6,
            market_sample_count=4,
            sector_by_ticker={"AAA": "TECH"},
            sector_returns={},
        )

        snapshot = build_market_snapshot(scan, analysis)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.market_context["session"], "scheduled_open")
        self.assertTrue(snapshot.market_context["schedule_verified"])
        self.assertEqual(
            snapshot.market_context["instrument_session"]["phase"], "main"
        )
        self.assertTrue(
            snapshot.market_context["instrument_session"]["trade_eligible"]
        )

        intelligence = IntelligencePipeline().analyze(snapshot)
        self.assertEqual(intelligence.symbol, "AAA")
        for number in range(1, 16):
            self.assertIsNotNone(getattr(intelligence, f"level_{number:02d}"))
        self.assertTrue(0.0 <= intelligence.overall_score <= 1.0)
        self.assertTrue(0.0 <= intelligence.overall_confidence <= 1.0)
        self.assertTrue(0.0 <= intelligence.overall_consistency <= 1.0)

        decisions = _evaluate_decisions(
            {"AAA": intelligence},
            SimpleNamespace(positions={}),
        )
        self.assertEqual(set(decisions), {"AAA"})
        self.assertIn(decisions["AAA"].action, {"BUY", "SELL", "HOLD", "WAIT"})

    def test_unknown_schedule_context_is_preserved_as_unknown(self):
        context = {
            "session": "unknown",
            "session_phase": "schedule_unavailable",
            "schedule_verified": False,
            "exchange_sessions": {},
            "instrument_session": {
                "session": "unknown",
                "verified": False,
                "is_open": False,
                "trade_eligible": False,
            },
        }
        self.assertFalse(context["schedule_verified"])
        self.assertEqual(context["instrument_session"]["trade_eligible"], False)


if __name__ == "__main__":
    unittest.main()
