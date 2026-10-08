"""RSRV v2 -- wzorzec (fitmodel/rsrv_v2.py). TE SAME przypadki i wyniki sa w QExt2 ReserveModelV2Test."""
import unittest

from fitmodel import rsrv_v2 as m


def run(n, p, hr, cp=240.0, lthr=148.0, base=0.0):
    s = m.ReserveState()
    for _ in range(n):
        m.tick(s, p, hr, cp, lthr)
    return m.percent(base, s.load), s.load


class TestRsrvV2(unittest.TestCase):
    def test_curve_points(self):
        self.assertAlmostEqual(m.rate_per_second(1.0) * 3600, 1.0, places=9)    # 1 h przy CP
        self.assertAlmostEqual(m.rate_per_second(0.8) * 3600, 0.25, places=9)   # 4 h przy 0,8 CP
        self.assertAlmostEqual(m.rate_per_second(0.6) * 3600, 1 / 13, places=9)
        self.assertEqual(m.rate_per_second(0.0), 0.0)

    def test_golden_cases(self):
        self.assertEqual(run(7200, 168, None)[0], 75)      # 2 h @ 0,7 CP
        self.assertEqual(run(3600, 192, None)[0], 75)      # 1 h @ 0,8 CP
        self.assertEqual(run(3600, 144, 148)[0], 86)       # tetno na progu przy 0,6 CP -> podbija
        self.assertEqual(run(3600, 0, None)[0], 100)       # zjazd / 0 W -> bez ubytku
        self.assertEqual(run(3600, 192, None, base=0.3)[0], 45)  # druga jazda tego dnia
        self.assertEqual(run(3600, 144, 250)[0], 92)       # tetno spoza zakresu ignorowane
        self.assertEqual(run(3000, 168, 125)[0], 90)       # normalne tetno nie zmienia wyniku

    def test_hr_never_lowers(self):
        self.assertEqual(run(3600, 192, 90)[0], run(3600, 192, None)[0])

    def test_percent_bounds(self):
        self.assertEqual(m.percent(0.0, 0.0), 100)
        self.assertEqual(m.percent(0.9, 0.5), 0)


if __name__ == "__main__":
    unittest.main()
