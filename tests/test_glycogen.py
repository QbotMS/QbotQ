"""Testy modelu glikogenu (offline, bez DB/FIT).

Glowny cel: straznik JEDNOSTEK cho_burn -- wczesniej brakowalo konwersji J->kcal
(/4184), przez co burn byl ~4184x za duzy i zerowal bak co jazde.
"""
import unittest

from fitmodel.glycogen import (
    _compute_cho_burn_rows,
    _compute_ride_kcal_rows,
    cho_fraction,
)


def _rows(power, n):
    return [{"timestamp": None, "power": power} for _ in range(n)]


class TestBurnUnits(unittest.TestCase):
    def test_burn_150w_1h_realistic(self):
        # 150 W przez godzine przy FTP 253 -> realnie ~50-90 g/h
        g = _compute_cho_burn_rows(_rows(150, 3600), 253.0)
        self.assertGreater(g, 40.0)
        self.assertLess(g, 120.0, "burn absurdalnie wysoki -> regresja bledu jednostek")

    def test_burn_220w_1h_realistic(self):
        g = _compute_cho_burn_rows(_rows(220, 3600), 253.0)
        self.assertGreater(g, 100.0)
        self.assertLess(g, 260.0)

    def test_burn_scales_with_power(self):
        lo = _compute_cho_burn_rows(_rows(120, 3600), 253.0)
        hi = _compute_cho_burn_rows(_rows(240, 3600), 253.0)
        self.assertGreater(hi, lo)

    def test_no_power_zero_burn(self):
        self.assertEqual(_compute_cho_burn_rows(_rows(None, 100), 253.0), 0.0)

    def test_zero_ftp_safe(self):
        self.assertEqual(_compute_cho_burn_rows(_rows(150, 100), 0), 0.0)

    def test_ride_kcal_sane(self):
        # 150 W / 1 h metabolicznie ~ 560 kcal (150/0.23/4184*3600)
        k = _compute_ride_kcal_rows(_rows(150, 3600))
        self.assertGreater(k, 400.0)
        self.assertLess(k, 750.0)


class TestChoFraction(unittest.TestCase):
    def test_bounds(self):
        self.assertAlmostEqual(cho_fraction(0.30), 0.50, places=2)
        self.assertAlmostEqual(cho_fraction(1.20), 0.95, places=2)

    def test_monotonic(self):
        vals = [cho_fraction(x / 100.0) for x in range(30, 120, 5)]
        self.assertEqual(vals, sorted(vals))


if __name__ == "__main__":
    unittest.main()
