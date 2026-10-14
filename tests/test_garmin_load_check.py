"""[GARMIN-DANE] Etap 6: walidacja ModelQ vs obciazenie Garmina."""
import math
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, "/opt/qbot/app")

from fitmodel.garmin_load_check import evaluate, fit  # noqa: E402

D0 = date(2026, 1, 1)


def mk(i, h, x, ratio):
    return {"id": str(i), "date": D0 + timedelta(days=i), "h": h, "x": x, "g": x * ratio}


def history(n=60):
    out = []
    for i in range(n):
        h = 1.0 + (i % 5)                       # 1..5 h
        base = 0.95 * h ** -0.25                 # Garmin zaniza dlugie jazdy
        noise = 1.0 + 0.08 * ((i % 7) - 3) / 3   # +-8%
        out.append(mk(i, h, 60 * h, base * noise))
    return out


class TestGarminLoadCheck(unittest.TestCase):
    def test_fit_recovers_duration_effect(self):
        m = fit(history())
        self.assertAlmostEqual(m["b"], -0.25, delta=0.05)
        self.assertLess(m["sd"], 0.1)

    def test_too_few(self):
        self.assertIsNone(fit(history(10)))

    def test_normal_long_ride_not_flagged(self):
        m = fit(history())
        p = mk(99, 5.0, 300, 0.95 * 5 ** -0.25)
        self.assertIsNone(evaluate(p, m)["flag"])

    def test_hr_high_flagged(self):
        m = fit(history())
        e = evaluate(mk(99, 1.0, 60, 0.95 * 1.6), m)
        self.assertEqual(e["flag"], "wyzej")
        self.assertIn("tętno wysoko", e["text"])
        self.assertGreater(e["dev_pct"], 40)

    def test_hr_low_flagged(self):
        m = fit(history())
        e = evaluate(mk(99, 2.0, 120, 0.95 * 2 ** -0.25 * 0.5), m)
        self.assertEqual(e["flag"], "nizej")
        self.assertIn("pas HR", e["text"])

    def test_expected_value(self):
        m = fit(history())
        e = evaluate(mk(99, 1.0, 100, 0.95), m)
        self.assertTrue(80 <= e["garmin_expected"] <= 110)


if __name__ == "__main__":
    unittest.main()
