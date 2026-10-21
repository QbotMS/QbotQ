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


class TestV2(unittest.TestCase):
    """v2 (21.10.2026): wygladzanie trendu, rampy, test schodkowy."""

    def test_detrend_removes_slow_trend(self):
        # szum bialy + silny powolny trend (tetno rosnie po starcie): bez wygladzania a1 zawyzone, z nim ~0.5
        # zmierzone 21.10: czysty szum ~0.58 (krotkie okno), z trendem ~0.67, po wygladzeniu = czysty szum
        rng = np.random.default_rng(5)
        raw, fixed, pure = [], [], []
        for _ in range(30):
            w = 20 * rng.normal(size=200)
            x = 800 + w + np.linspace(120, -120, 200)
            raw.append(h.dfa_a1(x)); fixed.append(h.dfa_a1(h.detrend_sp(x))); pure.append(h.dfa_a1(800 + w))
        self.assertGreater(np.mean(raw), np.mean(fixed) + 0.05)
        self.assertAlmostEqual(np.mean(fixed), np.mean(pure), delta=0.03)

    def test_detrend_keeps_pink_noise(self):
        rng = np.random.default_rng(9)
        vals = [h.dfa_a1(h.detrend_sp(800 + 30 * _pink(200, rng))) for _ in range(30)]
        self.assertAlmostEqual(float(np.mean(vals)), 1.0, delta=0.2)

    def test_gentle_ramp_is_steady_steep_is_not(self):
        rng = np.random.default_rng(4)
        gentle = np.linspace(170, 195, 120) + rng.normal(0, 10, 120)      # 12,5 W/min
        steep = np.linspace(150, 260, 120) + rng.normal(0, 10, 120)       # 55 W/min
        self.assertTrue(h.steady(gentle, [8] * 120)[0])
        self.assertFalse(h.steady(steep, [8] * 120)[0])

    def test_step_test_detected(self):
        rng = np.random.default_rng(2)
        p = np.concatenate([np.full(600, 110.0)] + [np.full(360, 140.0 + 20 * k) for k in range(5)] + [np.full(300, 100.0)])
        p = p + rng.normal(0, 8, len(p))
        st = h.detect_steps(np.arange(len(p)), p)
        self.assertGreaterEqual(len(st), 4)
        self.assertAlmostEqual(st[-1]["p"], 220, delta=6)       # rozgrzewka 110 W moze byc 1. stopniem

    def test_no_step_test_in_variable_ride(self):
        rng = np.random.default_rng(3)
        p = 180 + 60 * np.sin(np.arange(4000) / 37.0) + rng.normal(0, 25, 4000)
        self.assertEqual(h.detect_steps(np.arange(4000), p), [])


if __name__ == "__main__":
    unittest.main()
