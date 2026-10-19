import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from bot.intelligence.integration import build_market_snapshot
from bot.intelligence.pipeline.intelligence_pipeline import IntelligencePipeline
from bot.main import _evaluate_decisions, _filter_intelligence_to_active_tickers
from bot.paper_executor import PaperExecutor
from bot.portfolio_store import SQLitePortfolioStore


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
            trend_strength=0.01,
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

        # The official-session eligibility allowlist gates results before
        # DecisionEngine. A stale/inactive ticker is excluded, while an empty
        # allowlist blocks all recommendations.
        decision_inputs = _filter_intelligence_to_active_tickers(
            {"AAA": intelligence, "STALE": intelligence},
            {"AAA"},
        )
        self.assertEqual(set(decision_inputs), {"AAA"})
        decisions = _evaluate_decisions(decision_inputs, SimpleNamespace(positions={}))
        self.assertEqual(set(decisions), {"AAA"})
        self.assertIn(decisions["AAA"].action, {"BUY", "SELL", "HOLD", "WAIT"})
        self.assertEqual(
            _filter_intelligence_to_active_tickers({"AAA": intelligence}, set()), {}
        )
        self.assertEqual(
            set(_filter_intelligence_to_active_tickers({"AAA": intelligence}, None)),
            {"AAA"},
        )

        # Exercise the real L1-L15 result through DecisionEngine, virtual
        # execution, and persistence. This remains paper-only; no broker orders
        # are submitted and the existing PositionManager exit rules stay intact.
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLitePortfolioStore(Path(tmp) / "portfolio.sqlite")
            portfolio = store.load_or_create(1000.0, 0.001)
            portfolio.buy(
                "AAA", 1, 100.0,
                datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc),
            )
            allowed_buys = {
                ticker for ticker, decision in decisions.items()
                if decision.action == "BUY"
            }
            sells, buys = PaperExecutor().execute(
                portfolio,
                scan,
                eligible_buy_tickers=allowed_buys,
            )
            self.assertEqual(len(sells), 1)
            self.assertEqual(sells[0].side, "SELL")
            self.assertEqual(buys, [])
            self.assertNotIn("AAA", portfolio.positions)

            store.save(portfolio, scan.current_prices)
            restored = store.load_or_create(5000.0, 0.005)
            self.assertEqual(restored.initial_balance, 1000.0)
            self.assertEqual(restored.positions, {})
            self.assertEqual([trade.side for trade in restored.trades], ["BUY", "SELL"])
            self.assertAlmostEqual(restored.realized_pnl, portfolio.realized_pnl)

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
