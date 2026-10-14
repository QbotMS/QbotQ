"""[GARMIN-DANE] Etap 3: status HRV QBota."""
import math
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, "/opt/qbot/app")

from fitmodel.hrv_status import compute_series, current  # noqa: E402

D0 = date(2026, 1, 1)


def nights(values):
    return [(D0 + timedelta(days=i), v) for i, v in enumerate(values)]


BASE = [80, 76, 84, 78, 82, 79, 81, 77, 83, 80] * 6   # 60 nocy, srednio ~80, male wahania


class TestHrvStatus(unittest.TestCase):
    def test_too_little_history(self):
        s = compute_series(nights([80] * 20))
        self.assertTrue(all(r["status"] is None for r in s))
        self.assertIsNone(current(nights([80] * 20)))

    def test_norma(self):
        c = current(nights(BASE + [80] * 7))
        self.assertEqual(c["status"], "norma")
        self.assertEqual(c["level"], "good")
        self.assertTrue(c["lo"] < c["norm"] < c["hi"])

    def test_ponizej_and_nisko(self):
        self.assertIn(current(nights(BASE + [77] * 7))["status"], ("ponizej", "nisko"))
        self.assertEqual(current(nights(BASE + [65] * 7))["status"], "nisko")
        self.assertEqual(current(nights(BASE + [65] * 7))["label"], "nisko")

    def test_powyzej_is_not_alarm(self):
        c = current(nights(BASE + [95] * 7))
        self.assertEqual(c["status"], "powyzej")
        self.assertEqual(c["level"], "good")

    def test_avg7_is_geometric_mean_of_last_7(self):
        vals = BASE + [70, 72, 74, 76, 78, 80, 82]
        last = compute_series(nights(vals))[-1]
        exp = math.exp(sum(math.log(v) for v in vals[-7:]) / 7)
        self.assertAlmostEqual(last["avg7"], round(exp, 1))

    def test_skips_missing_and_zero(self):
        s = compute_series(nights(BASE + [None, 0, 80]))
        self.assertEqual(len(s), 61)


if __name__ == "__main__":
    unittest.main()
