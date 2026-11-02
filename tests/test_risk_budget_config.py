import os
import unittest
from unittest.mock import patch

from bot.config import Config


class TestVirtualRiskBudgetConfig(unittest.TestCase):
    def _load(self, **values):
        env = {
            "INVEST_TOKEN": "virtual-test-token",
            "VIRTUAL_RISK_BUDGET_PERCENT": "1.0",
        }
        env.update(values)
        with patch.dict(os.environ, env, clear=True):
            return Config.from_env()

    def test_defaults_to_one_percent_virtual_equity_risk_budget(self):
        config = self._load()
        self.assertEqual(config.risk_budget_percent, 1.0)

    def test_reads_configured_risk_budget(self):
        config = self._load(VIRTUAL_RISK_BUDGET_PERCENT="0.75")
        self.assertEqual(config.risk_budget_percent, 0.75)

    def test_rejects_risk_budget_outside_supported_range(self):
        for value in ("0", "-1", "100.01", "nan", "inf"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self._load(VIRTUAL_RISK_BUDGET_PERCENT=value)


if __name__ == "__main__":
    unittest.main()
