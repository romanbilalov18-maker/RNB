import unittest

from bot.main import _should_run_another_cycle


class MainCycleTimingTests(unittest.TestCase):
    def test_does_not_start_another_cycle_when_less_than_one_interval_remains(self):
        self.assertFalse(_should_run_another_cycle(299.0, 5.0))

    def test_does_not_start_another_cycle_at_exact_interval_boundary(self):
        self.assertFalse(_should_run_another_cycle(300.0, 5.0))

    def test_allows_another_cycle_when_more_than_one_interval_remains(self):
        self.assertTrue(_should_run_another_cycle(301.0, 5.0))

    def test_supports_different_cycle_intervals(self):
        self.assertFalse(_should_run_another_cycle(599.0, 10.0))
        self.assertTrue(_should_run_another_cycle(601.0, 10.0))


if __name__ == "__main__":
    unittest.main()
