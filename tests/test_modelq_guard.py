"""ModelQ: bezpieczniki (fitmodel/modelq_guard.py) -- czyste funkcje."""
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")

from fitmodel.modelq_guard import _pl, at_bound, clamp_streak, tp_diff_pct  # noqa: E402


class TestModelqGuard(unittest.TestCase):
    def test_at_bound(self):
        self.assertTrue(at_bound(18.16, 22.7, 0.8, 1.2))
        self.assertTrue(at_bound(22.0, 20.0, 0.9, 1.1))
        self.assertFalse(at_bound(20.0, 20.0, 0.9, 1.1))

    def test_streak(self):
        days = [(18.0, 20.0), (18.0, 20.0), (19.5, 20.0), (18.0, 20.0)]
        self.assertEqual(clamp_streak(days, 0.9, 1.1), 2)
        self.assertEqual(clamp_streak([(20.0, 20.0)], 0.9, 1.1), 0)

    def test_tp_diff(self):
        self.assertEqual(tp_diff_pct(238.8, 231.0), 3.4)
        self.assertIsNone(tp_diff_pct(None, 231.0))

    def test_pl(self):
        self.assertEqual(_pl(-22.24, True), "-22,2")
        self.assertEqual(_pl(20.0), "20,0")


if __name__ == "__main__":
    unittest.main()
