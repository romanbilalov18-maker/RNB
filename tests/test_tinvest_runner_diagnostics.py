import io
import unittest
from contextlib import redirect_stdout

from bot.intelligence.tinvest_runner import _print_read_only_status


class TInvestRunnerDiagnosticsTests(unittest.TestCase):
    def test_read_only_runner_reports_decision_engine_not_run_not_disconnected(self):
        output = io.StringIO()
        with redirect_stdout(output):
            _print_read_only_status()
        text = output.getvalue()
        self.assertIn("Trade execution: DISABLED", text)
        self.assertIn("Decision Engine: NOT RUN", text)
        self.assertIn("bot.main", text)
        self.assertNotIn("Decision Engine: NOT CONNECTED", text)


if __name__ == "__main__":
    unittest.main()
