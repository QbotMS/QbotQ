"""[GARMIN-DANE] Etap 7: dryf tetna i czas w upale."""
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")

from fitmodel.heat_drift import _pl, bucket, drift_from_halves  # noqa: E402


class TestHeatDrift(unittest.TestCase):
    def test_drift(self):
        h1 = {"p": 180.0, "hr": 120.0, "n": 3000}
        h2 = {"p": 180.0, "hr": 130.0, "n": 3000}
        self.assertEqual(drift_from_halves(h1, h2), 7.7)   # EF 1.5 -> 1.385

    def test_no_drift(self):
        h = {"p": 160.0, "hr": 115.0, "n": 2000}
        self.assertEqual(drift_from_halves(h, dict(h)), 0.0)

    def test_negative_drift_allowed(self):
        self.assertLess(drift_from_halves({"p": 150.0, "hr": 120.0, "n": 900}, {"p": 170.0, "hr": 120.0, "n": 900}), 0)

    def test_too_short_half(self):
        self.assertIsNone(drift_from_halves({"p": 150.0, "hr": 120.0, "n": 300}, {"p": 150.0, "hr": 125.0, "n": 3000}))
        self.assertIsNone(drift_from_halves(None, {"p": 1, "hr": 1, "n": 999}))

    def test_bucket(self):
        self.assertEqual([bucket(None), bucket(5), bucket(10), bucket(59.9), bucket(60)], [0, 0, 1, 1, 2])

    def test_pl(self):
        self.assertEqual(_pl(8.75), "8,8")


if __name__ == "__main__":
    unittest.main()
