import os
import unittest
from unittest.mock import patch

from bot.live_runner import LiveMarketRunner


class LiveMarketRunnerUniverseTests(unittest.TestCase):
    def test_default_analysis_universe_is_wider_than_previous_ten(self):
        with patch.dict(os.environ, {}, clear=True):
            runner = LiveMarketRunner(client=object())
        self.assertEqual(runner.max_analysis_instruments, 50)

    def test_analysis_universe_can_be_configured(self):
        with patch.dict(os.environ, {"TINVEST_MAX_ANALYSIS_INSTRUMENTS": "75"}):
            runner = LiveMarketRunner(client=object())
        self.assertEqual(runner.max_analysis_instruments, 75)

    def test_analysis_universe_rejects_non_positive_values(self):
        for value in ("0", "-5", "many"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"TINVEST_MAX_ANALYSIS_INSTRUMENTS": value}
            ):
                with self.assertRaises(ValueError):
                    LiveMarketRunner(client=object())


if __name__ == "__main__":
    unittest.main()
