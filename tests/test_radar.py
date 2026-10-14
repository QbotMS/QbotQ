"""Testy offline qbot_radar (bez sieci): siatka, kodowanie, wykrywanie ruchu, werdykt."""
import datetime as dt
import os
import shutil
import tempfile
import unittest

import numpy as np

os.environ["QBOT_RADAR_CACHE"] = tempfile.mkdtemp(prefix="radar_ut_")
import qbot_radar as R  # noqa: E402


def _blobs(shift_px=(0.0, 0.0), seed=1):
    """Syntetyczny opad: kilka plam (dBZ) przesunietych o shift_px (kolumna, wiersz)."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:R.H, 0:R.W]
    a = np.full((R.H, R.W), R.DBZ_NONE, np.float32)
    for _ in range(60):
        cx, cy = rng.uniform(0, R.W), rng.uniform(0, R.H)
        sx, sy = rng.uniform(4, 14), rng.uniform(4, 14)
        amp = rng.uniform(25, 45)
        g = amp * np.exp(-(((xx - cx - shift_px[0]) / sx) ** 2 + ((yy - cy - shift_px[1]) / sy) ** 2))
        a = np.maximum(a, g.astype(np.float32))
    return a


class RadarTest(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(R.CACHE, ignore_errors=True)
        os.makedirs(R.CACHE)

    def _save(self, ts, a):
        np.savez_compressed(R._fname(ts, "npz"), u=R._encode(a))

    def test_siatka_i_rzutowanie(self):
        b = R.bounds_latlon()
        self.assertAlmostEqual(b[0][0], 47.5, places=3)
        c, r = R.to_px(52.23, 21.01)
        self.assertTrue(0 < c < R.W and 0 < r < R.H)
        lon, lat = R._unmerc(R.X0 + c * R.PX_M, R.Y1 - r * R.PX_M)
        self.assertAlmostEqual(lat, 52.23, places=4)
        self.assertAlmostEqual(lon, 21.01, places=4)

    def test_kodowanie(self):
        a = np.array([[np.nan, R.DBZ_NONE, 18.0, 47.5]], np.float32)
        d = R._decode(R._encode(a))
        self.assertTrue(np.isnan(d[0, 0]))
        np.testing.assert_allclose(d[0, 1:], a[0, 1:], atol=0.25)

    def test_mm_na_h(self):
        self.assertEqual(R.dbz_to_mmh(5), 0.0)
        self.assertAlmostEqual(R.dbz_to_mmh(23), 1.0, places=1)

    def test_ruch_na_wschod(self):
        t1 = dt.datetime(2026, 10, 14, 6, 30, tzinfo=dt.timezone.utc)
        v = 0.6  # px/min na wschod
        for m in (30, 15, 0):
            self._save(t1 - dt.timedelta(minutes=m), _blobs((v * (30 - m), 0.0)))
        mot = R.motion()
        self.assertEqual(mot["status"], "OK")
        self.assertGreaterEqual(mot["n"], 5)
        lm = R.local_motion(52.23, 21.01, mot)
        self.assertEqual(lm["dokad"], "E")
        self.assertEqual(lm["skad"], "W")
        self.assertAlmostEqual(lm["vx"], v, delta=0.1)
        self.assertAlmostEqual(lm["vy"], 0.0, delta=0.1)

    def test_werdykt(self):
        h_sucho = [{"t": "08:00", "udzial": 0.0, "mmh": 0.0, "pokrycie": True}]
        h_pada = [{"t": "08:00", "udzial": 0.9, "mmh": 2.1, "pokrycie": True}]
        p = [{"t": "08:05", "udzial": 0.8, "mmh": 2.0}, {"t": "08:10", "udzial": 0.1, "mmh": 0.0}]
        lm = {"vx": 1}
        self.assertIn("dojdzie ok. 08:05", R._werdykt(h_sucho, p, lm))
        self.assertIn("przestanie ok. 08:10", R._werdykt(h_pada, p, lm))
        self.assertIn("Brak pokrycia", R._werdykt([{"pokrycie": False}], p, lm))


if __name__ == "__main__":
    unittest.main()
