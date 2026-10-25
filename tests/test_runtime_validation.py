import math
import os
import unittest
from unittest.mock import patch

from bot.main import _env_positive_float, _should_run_another_cycle


class RuntimeValidationTests(unittest.TestCase):
    def test_accepts_positive_finite_value(self):
        with patch.dict(os.environ, {"RNB_TEST_MINUTES": "2.5"}):
            self.assertEqual(_env_positive_float("RNB_TEST_MINUTES", 1.0), 2.5)

    def test_uses_default_when_variable_is_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_env_positive_float("RNB_TEST_MISSING", 3.0), 3.0)

    def test_rejects_zero_and_negative_values(self):
        for raw in ("0", "-1", "-0.01"):
            with self.subTest(raw=raw), patch.dict(os.environ, {"RNB_TEST_MINUTES": raw}):
                with self.assertRaisesRegex(ValueError, "positive finite number"):
                    _env_positive_float("RNB_TEST_MINUTES", 1.0)

    def test_rejects_nan_and_infinities(self):
        for raw in ("nan", "NaN", "inf", "-inf", "Infinity", "1e999"):
            with self.subTest(raw=raw), patch.dict(os.environ, {"RNB_TEST_MINUTES": raw}):
                with self.assertRaisesRegex(ValueError, "positive finite number"):
                    _env_positive_float("RNB_TEST_MINUTES", 1.0)

    def test_rejects_non_numeric_value(self):
        with patch.dict(os.environ, {"RNB_TEST_MINUTES": "five"}):
            with self.assertRaisesRegex(ValueError, "positive finite number"):
                _env_positive_float("RNB_TEST_MINUTES", 1.0)

    def test_cycle_requires_more_than_one_full_interval(self):
        self.assertTrue(_should_run_another_cycle(301.0, 5.0))
        self.assertFalse(_should_run_another_cycle(300.0, 5.0))
        self.assertFalse(_should_run_another_cycle(12.0, 5.0))


if __name__ == "__main__":
    unittest.main()
