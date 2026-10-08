"""Dynamiczne LTHR (fitmodel/lthr.py) -- czyste funkcje."""
import sys, unittest
sys.path.insert(0, "/opt/qbot/app")
from fitmodel import lthr as L


class T(unittest.TestCase):
    def test_publish_first_value_and_seed(self):
        self.assertEqual(L.publish_step(151.6, None, None), 152)
        self.assertEqual(L.publish_step(None, None, None), L.SEED_BPM)

    def test_hysteresis(self):
        self.assertEqual(L.publish_step(149.2, 148, 148), 148)      # < 2 ud. -> bez zmian
        self.assertEqual(L.publish_step(None, 148, 148), 148)       # brak danych -> bez zmian

    def test_week_limit(self):
        self.assertEqual(L.publish_step(160.0, 148, 148), 151)      # max +3 wzgledem tygodnia wstecz
        self.assertEqual(L.publish_step(130.0, 148, 149), 146)      # max -3

    def test_raw_estimate_thresholds(self):
        pts = [("a", 0.8, 140.0, 15.0)] * 12
        self.assertIsNone(L.raw_estimate(pts, 80)[0])                # 1 jazda < 4
        pts = [(e, 0.8, 140.0, 15.0) for e in "abcd" for _ in range(3)]
        raw, n, nr = L.raw_estimate(pts, 80)
        self.assertAlmostEqual(raw, 140 + 80 * 0.2)
        self.assertEqual((n, nr), (12, 4))

    def test_raw_estimate_skips_heat_and_low_pct(self):
        pts = [(e, 0.8, 140.0, 30.0) for e in "abcd" for _ in range(3)] + [(e, 0.5, 120.0, 15.0) for e in "abcd" for _ in range(3)]
        self.assertIsNone(L.raw_estimate(pts, 80)[0])

    def test_slope_within_ride(self):
        pts = [(e, p, 100 + 60 * p) for e in "abcdefgh" for p in (0.6, 0.7, 0.8, 0.9)]
        k, n = L.within_ride_slope(pts)
        self.assertAlmostEqual(k, 60.0)
        self.assertEqual(n, 8)
        self.assertEqual(L.within_ride_slope(pts[:8])[0], L.SLOPE_DEFAULT)   # za malo jazd

    def test_windows(self):
        rows = [(i, 200, 140, 15.0) for i in range(2000)]
        w = L.ride_windows(rows)
        self.assertTrue(w and w[0][0] == L.WARMUP_S and w[0][1] == 200 and w[0][2] == 140)
        rows2 = [(i, 0 if i % 10 == 0 else 200, 140, 15.0) for i in range(2000)]    # 10 % toczenia -> odrzucone
        self.assertEqual(L.ride_windows(rows2), [])


class TempFactor(unittest.TestCase):
    def test_temp_factor(self):
        from fitmodel.modelq2.hr_xss import temp_factor
        self.assertEqual(temp_factor(None, 1.0, 0.01), 1.0)
        self.assertEqual(temp_factor(20, None, None), 1.0)
        self.assertAlmostEqual(temp_factor(15, 1.0, 0.01), 1.0)
        self.assertLess(temp_factor(25, 1.0, 0.01), 1.0)          # cieplo -> XSS z tetna w dol
        self.assertEqual(temp_factor(60, 1.0, 0.05), 0.80)        # przyciecie
        self.assertEqual(temp_factor(-30, 1.0, 0.05), 1.0)        # r <= 0 -> bez korekty


if __name__ == "__main__":
    unittest.main()
