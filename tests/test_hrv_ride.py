"""Testy fitmodel/hrv_ride.py (HRV z jazdy, DFA a1) -- sygnaly o znanym wykladniku + czyszczenie + regresja."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
from fitmodel import hrv_ride as h  # noqa: E402


def _pink(n, rng):
    f = np.fft.rfftfreq(n)
    f[0] = 1
    spec = (rng.normal(size=len(f)) + 1j * rng.normal(size=len(f))) / np.sqrt(f)
    x = np.fft.irfft(spec, n)
    return x / x.std()


class TestDfa(unittest.TestCase):
    def _mean_a1(self, gen):
        rng = np.random.default_rng(7)
        vals = [h.dfa_a1(800 + 30 * gen(160, rng)) for _ in range(40)]
        return float(np.mean(vals))

    def test_white_noise_half(self):
        self.assertAlmostEqual(self._mean_a1(lambda n, r: r.normal(size=n)), 0.5, delta=0.1)

    def test_pink_noise_one(self):
        self.assertAlmostEqual(self._mean_a1(_pink), 1.0, delta=0.15)

    def test_brown_noise_one_and_half(self):
        self.assertAlmostEqual(self._mean_a1(lambda n, r: np.cumsum(r.normal(size=n)) / 3), 1.5, delta=0.15)

    def test_too_short(self):
        self.assertIsNone(h.dfa_a1([800] * 20))


class TestClean(unittest.TestCase):
    def test_marks_and_fixes_artifacts(self):
        rr = [800.0] * 50
        rr[10] = 1600   # zgubione uderzenie
        rr[30] = 250    # poza zakresem
        y, bad = h.clean_rr(rr)
        self.assertTrue(bad[10] and bad[30])
        self.assertEqual(int(bad.sum()), 2)
        self.assertAlmostEqual(y[10], 800, delta=1)


class TestRegress(unittest.TestCase):
    def test_finds_ltp_and_tp(self):
        rng = np.random.default_rng(1)
        P = rng.uniform(120, 260, 40)
        A1 = 1.25 - (P - 120) * (0.8 / 140) + rng.normal(0, 0.04, 40)   # 0.75 przy ~207 W, 0.5 przy ~251 W
        r = h.regress(P, A1)
        self.assertAlmostEqual(r["ltp_w"], 207, delta=8)
        self.assertEqual(r["conf_ltp"], "wysoka")
        self.assertAlmostEqual(r["tp_w"], 251, delta=10)

    def test_no_result_without_spread(self):
        r = h.regress([150] * 10, [0.9] * 10)
        self.assertIsNone(r["ltp_w"])

    def test_extrapolated_is_low_confidence(self):
        P = np.linspace(100, 150, 12)
        A1 = 1.3 - (P - 100) * 0.004       # a1 1.30..1.10 -- 0.75 daleko poza zakresem
        r = h.regress(P, A1)
        self.assertEqual(r["conf_ltp"], "niska")
        self.assertIsNone(r["tp_w"])


class TestSteady(unittest.TestCase):
    def test_steady_and_not(self):
        rng = np.random.default_rng(3)
        ok, p = h.steady(200 + rng.normal(0, 15, 120), [8] * 120)
        self.assertTrue(ok)
        self.assertAlmostEqual(p, 200, delta=5)
        bad_p = np.r_[np.full(60, 350.0), np.zeros(60)]
        self.assertFalse(h.steady(bad_p, [8] * 120)[0])
        self.assertFalse(h.steady(200 + rng.normal(0, 15, 120), [0] * 120)[0])


if __name__ == "__main__":
    unittest.main()
