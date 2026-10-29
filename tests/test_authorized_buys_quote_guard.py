from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace

from bot.main import _authorized_buys


class AuthorizedBuysQuoteGuardTests(unittest.TestCase):
    def test_blocks_all_new_entries_when_any_held_quote_is_missing(self):
        decisions = {
            "AAA": SimpleNamespace(action="BUY", reason="signal approved"),
            "BBB": SimpleNamespace(action="WAIT", reason="no signal"),
        }
        output = StringIO()
        with redirect_stdout(output):
            tickers, reasons = _authorized_buys(decisions, ["ELMT", "SLAV"])

        self.assertEqual(tickers, set())
        self.assertEqual(reasons, {})
        self.assertIn("NEW ENTRIES BLOCKED", output.getvalue())
        self.assertIn("ELMT, SLAV", output.getvalue())

    def test_keeps_only_explicit_buy_decisions_when_all_held_quotes_are_fresh(self):
        decisions = {
            "AAA": SimpleNamespace(action="BUY", reason="signal approved"),
            "BBB": SimpleNamespace(action="WAIT", reason="no signal"),
            "CCC": SimpleNamespace(action="HOLD", reason="already held"),
        }

        tickers, reasons = _authorized_buys(decisions, [])

        self.assertEqual(tickers, {"AAA"})
        self.assertEqual(reasons, {"AAA": "signal approved"})

    def test_missing_quotes_never_authorize_entries_even_with_buy_signal(self):
        decisions = {"AAA": SimpleNamespace(action="BUY", reason="signal approved")}

        tickers, reasons = _authorized_buys(decisions, ["CARM"])

        self.assertFalse(tickers)
        self.assertFalse(reasons)


if __name__ == "__main__":
    unittest.main()
