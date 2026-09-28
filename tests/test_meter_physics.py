"""fitmodel/meter_physics.py: moc z fizyki na podjazdach (syntetycznie) + wzorzec na zywej bazie."""
import os
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from fitmodel import meter_physics as MP  # noqa: E402


def climb(mass, grade=0.06, v=3.0, scale=1.0, secs=900, temp=15.0):
    rho = 1.225 * 288.15 / (273.15 + temp)
    p = mass * MP.G * v * (grade + MP.CRR) + 0.5 * rho * MP.CDA * v ** 3
    return [(s, 100 + s * v * grade, s * v, int(round(p * scale)), 80, v, temp) for s in range(secs)]


class Physics(unittest.TestCase):
    def test_true_meter_ratio_one(self):
        n, r = MP.ride_ratio(climb(115.0), 115.0)
        self.assertGreater(n, 5)
        self.assertAlmostEqual(r, 1.0, delta=0.02)

    def test_overreading_meter_detected(self):
        n, r = MP.ride_ratio(climb(115.0, scale=1.35), 115.0)
        self.assertAlmostEqual(r, 1.35, delta=0.03)

    def test_flat_ride_no_result(self):
        n, r = MP.ride_ratio(climb(115.0, grade=0.0), 115.0)
        self.assertEqual(n, 0)
        self.assertIsNone(r)

    def test_luggage(self):
        import datetime as dt
        self.assertEqual(MP.luggage_kg(dt.date(2026, 6, 7)), 10.0)
        self.assertEqual(MP.luggage_kg(dt.date(2026, 9, 7)), 0.0)

    def test_reference_live(self):
        from fitmodel.ftp_resolver import _db_connect
        import datetime as dt
        c = _db_connect()
        try:
            ref, n = MP.reference_ratio(c, dt.date(2026, 7, 4), dt.date(2026, 8, 20))
        finally:
            c.close()
        if not n:
            self.skipTest("brak jazd wzorcowych")
        self.assertTrue(0.85 <= ref <= 1.15, ref)


if __name__ == "__main__":
    unittest.main()
