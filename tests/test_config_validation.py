import os
import unittest
from unittest.mock import patch

from bot.config import Config


class TestConfigValidation(unittest.TestCase):
    def _load(self, **overrides):
        env = {
            "INVEST_TOKEN": "test-token",
            "VIRTUAL_INITIAL_BALANCE": "10000",
            "VIRTUAL_COMMISSION_RATE": "0.0005",
            "TAKE_PROFIT_PERCENT": "0.15",
            "VIRTUAL_PORTFOLIO_DB": "data/test.sqlite3",
        }
        env.update(overrides)
        with patch.dict(os.environ, env, clear=True):
            return Config.from_env()

    def test_accepts_valid_numeric_configuration(self):
        config = self._load()
        self.assertEqual(config.initial_virtual_balance, 10000)
        self.assertEqual(config.commission_rate, 0.0005)
        self.assertEqual(config.take_profit_percent, 0.15)

    def test_rejects_non_finite_numeric_settings(self):
        for key in (
            "VIRTUAL_INITIAL_BALANCE",
            "VIRTUAL_COMMISSION_RATE",
            "TAKE_PROFIT_PERCENT",
        ):
            for value in ("nan", "inf", "-inf"):
                with self.subTest(key=key, value=value):
                    with self.assertRaisesRegex(ValueError, "finite number"):
                        self._load(**{key: value})

    def test_rejects_non_numeric_settings(self):
        for key in (
            "VIRTUAL_INITIAL_BALANCE",
            "VIRTUAL_COMMISSION_RATE",
            "TAKE_PROFIT_PERCENT",
        ):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    self._load(**{key: "not-a-number"})

    def test_rejects_non_positive_balance(self):
        with self.assertRaisesRegex(ValueError, "must be positive"):
            self._load(VIRTUAL_INITIAL_BALANCE="0")

    def test_rejects_negative_commission(self):
        with self.assertRaisesRegex(ValueError, "must not be negative"):
            self._load(VIRTUAL_COMMISSION_RATE="-0.01")

    def test_rejects_take_profit_below_minimum(self):
        with self.assertRaisesRegex(ValueError, "at least 0.15%"):
            self._load(TAKE_PROFIT_PERCENT="0.1")


if __name__ == "__main__":
    unittest.main()
